// Package securefile opens, writes, and removes files below a trusted
// directory without following links, and it sets their final modes.
//
// The owner of a directory opens it with OpenDir. Each method of Dir takes an
// untrusted relative path with / separators below that directory. The
// package checks the lexical rules of the path before any system call, and
// it opens each component without following a link, so a link anywhere in
// the path is an error, also a link that stays inside the directory. On
// Linux and macOS it walks directory descriptors (ADR-066). On Windows it
// walks through [os.Root] one component at a time and refuses each link.
//
// The rules and the reason codes are those of the Python utils/pathsafe.py
// module. On Windows, a mode sets only the read-only attribute, as
// [os.Chmod] does, and the private rules of ReplacePrivate and PrivateSubdir do not
// apply.
package securefile

import (
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync/atomic"
	"syscall"
)

// Reason names the rule that a path or a file breaks.
type Reason string

// The reasons that an Error reports. ReasonInvalidName reports a name that
// the platform cannot represent, and ReasonModeNotKept reports a file system
// that did not keep the mode that a write set. The others are the reason
// codes of utils/pathsafe.py.
const (
	ReasonNotRelative        Reason = "not_relative"
	ReasonNULByte            Reason = "nul_byte"
	ReasonEmptyComponent     Reason = "empty_component"
	ReasonDotComponent       Reason = "dot_component"
	ReasonTraversal          Reason = "traversal"
	ReasonInvalidName        Reason = "invalid_name"
	ReasonSymlink            Reason = "symlink"
	ReasonNotFound           Reason = "not_found"
	ReasonNotRegularFile     Reason = "not_regular_file"
	ReasonBaseDirUnavailable Reason = "base_dir_unavailable"
	ReasonOpenFailed         Reason = "open_failed"
	ReasonNotPrivate         Reason = "not_private"
	ReasonModeNotKept        Reason = "mode_not_kept"
)

// Error reports an operation on a path that a rule refused. It holds no file
// content.
type Error struct {
	Op     string // The operation, such as replace or open.
	Path   string // The path, as the caller gave it.
	Reason Reason
	Err    error // The cause from the system, or nil.
}

func (e *Error) Error() string {
	text := "securefile: " + e.Op + " " + e.Path + ": " + string(e.Reason)
	if e.Err != nil {
		text += ": " + e.Err.Error()
	}
	return text
}

func (e *Error) Unwrap() error { return e.Err }

// IsReason reports whether err is an *Error with the reason r.
func IsReason(err error, r Reason) bool {
	e, ok := errors.AsType[*Error](err)
	return ok && e.Reason == r
}

// privateFileMode is the mode of the files that the package creates.
const privateFileMode fs.FileMode = 0o600

// The mode of the directories that the package creates, and the mode bits
// that the private rules clear on a directory.
const (
	privateDirMode     = 0o700
	groupOrOtherAccess = 0o077
	groupOrOtherWrite  = 0o022
)

// dirRule selects how a walk opens and treats each directory.
type dirRule int

const (
	// ruleSearch opens each directory to search it only.
	ruleSearch dirRule = iota
	// ruleOpen opens each directory for reading, so that the walk can list
	// or sync it.
	ruleOpen
	// ruleCreate also creates each missing directory with the mode 0700.
	ruleCreate
	// ruleRestrict also clears group and other write on each directory.
	ruleRestrict
	// rulePrivate also requires that the caller owns each directory.
	rulePrivate
)

// Dir is a directory that its owner trusts. A Dir is safe for concurrent
// use. After Close, each method returns an error.
type Dir struct {
	h      dirHandle
	closed atomic.Bool
}

// OpenDir opens the directory at path, which the caller trusts. The path can
// hold links. The caller closes the Dir.
func OpenDir(path string) (*Dir, error) {
	h, err := openDirHandle(path)
	if err != nil {
		return nil, err
	}
	return &Dir{h: h}, nil
}

// Close closes the directory. A second Close returns an error that matches
// [fs.ErrClosed].
func (d *Dir) Close() error {
	if d.closed.Swap(true) {
		return failure("close dir", ".", fs.ErrClosed)
	}
	return d.h.close()
}

// CheckPath checks the lexical rules of an untrusted relative path, without
// access to a file.
func CheckPath(name string) error {
	_, err := components("check", name)
	return err
}

// Open opens the regular file name for reading.
func (d *Dir) Open(name string) (*os.File, error) {
	return d.open("open", name)
}

// ReadFile returns the content of the regular file name.
func (d *Dir) ReadFile(name string) (data []byte, err error) {
	file, err := d.open("read", name)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, failure("read", name, file.Close())) }()
	data, err = io.ReadAll(file)
	return data, failure("read", name, err)
}

func (d *Dir) open(op, name string) (*os.File, error) {
	parts, err := components(op, name)
	if err != nil {
		return nil, err
	}
	return d.h.openFile(op, name, parts)
}

// ReadDirNames returns the sorted names of the entries of the directory
// name.
func (d *Dir) ReadDirNames(name string) ([]string, error) {
	parts, err := components("list", name)
	if err != nil {
		return nil, err
	}
	names, err := d.h.readDirNames("list", name, parts)
	slices.Sort(names)
	return names, err
}

// Subdir opens the existing directory name.
func (d *Dir) Subdir(name string) (*Dir, error) {
	return d.subdir("subdir", name, ruleOpen)
}

// MakeSubdir opens the directory name, and first creates each missing
// directory of name with the mode 0700.
func (d *Dir) MakeSubdir(name string) (*Dir, error) {
	return d.subdir("make subdir", name, ruleCreate)
}

// PrivateSubdir opens the directory name for private state, and first
// creates each missing directory of name with the mode 0700. The caller must
// own each directory of name. Each loses group and other write, and the last
// also loses group and other access.
func (d *Dir) PrivateSubdir(name string) (*Dir, error) {
	return d.subdir("private subdir", name, rulePrivate)
}

func (d *Dir) subdir(op, name string, rule dirRule) (*Dir, error) {
	parts, err := components(op, name)
	if err != nil {
		return nil, err
	}
	h, err := d.h.subdir(op, name, parts, rule)
	if err != nil {
		return nil, err
	}
	return &Dir{h: h}, nil
}

// CreateOnce creates the file name with the content data and the mode 0600,
// and first creates each missing directory with the mode 0700. The file
// appears complete or not at all. When name exists, CreateOnce returns an
// error that matches [fs.ErrExist].
func (d *Dir) CreateOnce(name string, data []byte) error {
	parts, err := components("create once", name)
	if err != nil {
		return err
	}
	return d.h.createOnce("create once", name, parts, data)
}

// Replace creates or replaces the file name with the content data and the
// mode perm, and first creates each missing directory with the mode 0700.
// The file changes completely or not at all. An existing name must be a
// regular file.
func (d *Dir) Replace(name string, data []byte, perm fs.FileMode) error {
	parts, err := components("replace", name)
	if err != nil {
		return err
	}
	return d.h.replace("replace", name, parts, data, perm, ruleCreate)
}

// ReplacePrivate creates or replaces the file name with the content data and
// the mode 0600, as Replace does. Each directory below d loses group and
// other write, and the caller must own the parent of the file, which loses
// group and other access. d itself does not change.
func (d *Dir) ReplacePrivate(name string, data []byte) error {
	parts, err := components("replace private", name)
	if err != nil {
		return err
	}
	return d.h.replace("replace private", name, parts, data, privateFileMode, ruleRestrict)
}

// Chmod sets the mode of the regular file name to perm.
func (d *Dir) Chmod(name string, perm fs.FileMode) error {
	parts, err := components("chmod", name)
	if err != nil {
		return err
	}
	return d.h.chmod("chmod", name, parts, perm)
}

// RestrictToOwner lets only the current user use the regular file name. On
// Linux and macOS it sets the mode 0600. On Windows it sets a protected
// access list that lets only the current user read the file, as core/ssh.py
// does with icacls.
func (d *Dir) RestrictToOwner(name string) error {
	parts, err := components("restrict to owner", name)
	if err != nil {
		return err
	}
	return d.h.restrictToOwner("restrict to owner", name, parts)
}

// Remove removes the regular file name. An absent file or directory is not
// an error.
func (d *Dir) Remove(name string) error {
	parts, err := components("remove", name)
	if err != nil {
		return err
	}
	return d.h.remove("remove", name, parts)
}

// RemoveAll removes name and, when it is a directory, all that it holds. It
// removes a link inside the directory as an entry and never follows it. An
// absent name is not an error.
func (d *Dir) RemoveAll(name string) error {
	parts, err := components("remove all", name)
	if err != nil {
		return err
	}
	return d.h.removeAll("remove all", name, parts)
}

// components checks the lexical rules of an untrusted relative path and
// returns its components. The rules are those of pathsafe, and then the name
// must be one that the platform can represent.
func components(op, name string) ([]string, error) {
	if strings.ContainsRune(name, 0) {
		return nil, &Error{Op: op, Path: name, Reason: ReasonNULByte}
	}
	if name == "" {
		return nil, &Error{Op: op, Path: name, Reason: ReasonEmptyComponent}
	}
	if strings.HasPrefix(name, "/") {
		return nil, &Error{Op: op, Path: name, Reason: ReasonNotRelative}
	}
	parts := strings.Split(name, "/")
	for _, part := range parts {
		if reason := componentReason(part); reason != "" {
			return nil, &Error{Op: op, Path: name, Reason: reason}
		}
	}
	if _, err := filepath.Localize(name); err != nil {
		return nil, &Error{Op: op, Path: name, Reason: ReasonInvalidName}
	}
	return parts, nil
}

// componentReason returns the rule that one component breaks, or "".
func componentReason(part string) Reason {
	if part == "" {
		return ReasonEmptyComponent
	}
	if part == "." {
		return ReasonDotComponent
	}
	if part == ".." {
		return ReasonTraversal
	}
	return ""
}

// openReason classifies a failed open of a component as pathsafe does: a
// link is symlink, an absent entry or an entry that is not a directory is
// not_found, and another cause is open_failed.
func openReason(err error, entryIsLink bool) Reason {
	if entryIsLink || errors.Is(err, syscall.ELOOP) {
		return ReasonSymlink
	}
	if errors.Is(err, fs.ErrNotExist) || errors.Is(err, syscall.ENOTDIR) {
		return ReasonNotFound
	}
	return ReasonOpenFailed
}

// fill writes data to a new file, gives it the mode perm, and syncs it. The
// mode comes before the sync, so that the sync also persists the mode.
func fill(op, path string, file *os.File, data []byte, perm fs.FileMode) error {
	if _, err := file.Write(data); err != nil {
		return failure(op, path, err)
	}
	return errors.Join(setMode(op, path, file, perm), failure(op, path, file.Sync()))
}

// absentIsDone returns nil for an entry that is absent, for example because
// another process removed it first.
func absentIsDone(op, path string, err error) error {
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	return failure(op, path, err)
}

// tempName returns an unpredictable name for a temporary file beside leaf.
func tempName(leaf string) string {
	return "." + leaf + "." + rand.Text() + ".tmp"
}

// failure adds the operation and the path to an error from the system. It
// returns nil and an *Error unchanged.
func failure(op, path string, err error) error {
	if _, ok := errors.AsType[*Error](err); err == nil || ok {
		return err
	}
	return fmt.Errorf("securefile: %s %s: %w", op, path, err)
}
