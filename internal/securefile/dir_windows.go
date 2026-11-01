//go:build windows

package securefile

import (
	"errors"
	"fmt"
	"io/fs"
	"os"

	"golang.org/x/sys/windows"
)

// dirHandle is an open directory.
type dirHandle struct{ root *os.Root }

func openDirHandle(path string) (dirHandle, error) {
	root, err := os.OpenRoot(path)
	if err != nil {
		return dirHandle{}, &Error{Op: "open dir", Path: path, Reason: ReasonBaseDirUnavailable, Err: err}
	}
	return dirHandle{root: root}, nil
}

func (h dirHandle) close() error {
	return failure("close dir", ".", h.root.Close())
}

// walk opens the directories dirs below h one at a time, and refuses each
// link. It returns a new root of the last one, or of h when dirs is empty.
// The caller closes it.
func (h dirHandle) walk(op, path string, dirs []string, rule dirRule) (dirHandle, error) {
	root, err := h.root.OpenRoot(".")
	if err != nil {
		return dirHandle{}, failure(op, path, err)
	}
	cur := dirHandle{root: root}
	for _, name := range dirs {
		next, err := openDir(op, path, cur.root, name, rule)
		err = errors.Join(err, cur.close())
		if err != nil {
			return dirHandle{}, err
		}
		cur = next
	}
	return cur, nil
}

// walkParent walks to the parent of the last component of parts and returns
// it with the name of the last component.
func (h dirHandle) walkParent(op, path string, parts []string, rule dirRule) (dirHandle, string, error) {
	parent, err := h.walk(op, path, parts[:len(parts)-1], rule)
	return parent, parts[len(parts)-1], err
}

// openDir opens the directory name under parent, and refuses it when the
// entry is a link or is not the directory that the open reached. Modes do
// not apply on Windows, so each rule from ruleCreate on only creates a
// missing directory.
func openDir(op, path string, parent *os.Root, name string, rule dirRule) (dirHandle, error) {
	if rule >= ruleCreate {
		if err := parent.Mkdir(name, privateDirMode); err != nil && !errors.Is(err, fs.ErrExist) {
			return dirHandle{}, componentError(op, path, parent, name, err)
		}
	}
	sub, err := parent.OpenRoot(name)
	if err != nil {
		return dirHandle{}, componentError(op, path, parent, name, err)
	}
	d := dirHandle{root: sub}
	opened, err := sub.Stat(".")
	if err == nil {
		err = sameEntry(op, path, parent, name, opened)
	}
	if err != nil {
		return dirHandle{}, errors.Join(failure(op, path, err), d.close())
	}
	return d, nil
}

// sameEntry refuses the entry name under parent when it is a link or another
// reparse point, or when it is not the file that the open reached.
func sameEntry(op, path string, parent *os.Root, name string, opened fs.FileInfo) error {
	entry, err := parent.Lstat(name)
	if err != nil {
		return componentError(op, path, parent, name, err)
	}
	if isLink(entry) || !os.SameFile(entry, opened) {
		return &Error{Op: op, Path: path, Reason: ReasonSymlink}
	}
	return nil
}

// isLink reports whether an entry is a link or another reparse point, for
// example a junction.
func isLink(entry fs.FileInfo) bool {
	return entry.Mode()&(fs.ModeSymlink|fs.ModeIrregular) != 0
}

// componentError reports why name could not be opened under parent.
func componentError(op, path string, parent *os.Root, name string, err error) error {
	entry, lerr := parent.Lstat(name)
	return &Error{Op: op, Path: path, Reason: openReason(err, lerr == nil && isLink(entry)), Err: err}
}

func (h dirHandle) openFile(op, path string, parts []string) (file *os.File, err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleSearch)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, parent.close()) }()
	file, err = parent.root.OpenFile(leaf, os.O_RDONLY, 0)
	if err != nil {
		return nil, componentError(op, path, parent.root, leaf, err)
	}
	if err = checkOpened(op, path, parent.root, leaf, file); err != nil {
		return nil, errors.Join(err, failure(op, path, file.Close()))
	}
	return file, nil
}

// checkOpened refuses an opened leaf that is not a regular file, or whose
// entry is a link or another file.
func checkOpened(op, path string, parent *os.Root, leaf string, file *os.File) error {
	opened, err := file.Stat()
	if err != nil {
		return failure(op, path, err)
	}
	if err := sameEntry(op, path, parent, leaf, opened); err != nil {
		return err
	}
	if !opened.Mode().IsRegular() {
		return &Error{Op: op, Path: path, Reason: ReasonNotRegularFile}
	}
	return nil
}

func (h dirHandle) readDirNames(op, path string, parts []string) (names []string, err error) {
	d, err := h.walk(op, path, parts, ruleOpen)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, d.close()) }()
	dir, err := d.root.Open(".")
	if err != nil {
		return nil, failure(op, path, err)
	}
	defer func() { err = errors.Join(err, failure(op, path, dir.Close())) }()
	names, err = dir.Readdirnames(-1)
	return names, failure(op, path, err)
}

func (h dirHandle) subdir(op, path string, parts []string, rule dirRule) (dirHandle, error) {
	return h.walk(op, path, parts, rule)
}

func (h dirHandle) createOnce(op, path string, parts []string, data []byte) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleCreate)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, parent.close()) }()
	name, err := writeTemp(op, path, parent.root, leaf, data, privateFileMode)
	if err != nil {
		return err
	}
	// A hard link publishes the complete file and fails when the name exists.
	published := parent.root.Link(name, leaf)
	return failure(op, path, errors.Join(published, parent.root.Remove(name)))
}

// replace walks with rule. The private rules do not apply on Windows.
func (h dirHandle) replace(op, path string, parts []string, data []byte, perm fs.FileMode, rule dirRule) error {
	parent, leaf, err := h.walkParent(op, path, parts, rule)
	if err != nil {
		return err
	}
	err = replaceIn(op, path, parent.root, leaf, data, perm)
	return errors.Join(err, parent.close())
}

// replaceIn replaces leaf under parent.
func replaceIn(op, path string, parent *os.Root, leaf string, data []byte, perm fs.FileMode) error {
	if err := checkLeaf(op, path, parent, leaf); err != nil {
		return err
	}
	return publish(op, path, parent, leaf, data, perm)
}

// publish writes a temporary file beside leaf and renames it onto leaf.
func publish(op, path string, parent *os.Root, leaf string, data []byte, perm fs.FileMode) error {
	name, err := writeTemp(op, path, parent, leaf, data, perm)
	if err != nil {
		return err
	}
	if err := parent.Rename(name, leaf); err != nil {
		return failure(op, path, errors.Join(err, parent.Remove(name)))
	}
	return nil
}

// checkLeaf refuses an existing leaf that is a link or not a regular file.
func checkLeaf(op, path string, parent *os.Root, leaf string) error {
	entry, err := parent.Lstat(leaf)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if isLink(entry) {
		return &Error{Op: op, Path: path, Reason: ReasonSymlink}
	}
	if !entry.Mode().IsRegular() {
		return &Error{Op: op, Path: path, Reason: ReasonNotRegularFile}
	}
	return nil
}

// writeTemp writes data to a new temporary file beside leaf, gives it the
// mode perm, syncs it, and returns its name. It removes the file after a
// failure.
func writeTemp(op, path string, parent *os.Root, leaf string, data []byte, perm fs.FileMode) (string, error) {
	name := tempName(leaf)
	file, err := parent.OpenFile(name, os.O_RDWR|os.O_CREATE|os.O_EXCL, privateFileMode)
	if err != nil {
		return "", &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if err := errors.Join(fill(op, path, file, data, perm), failure(op, path, file.Close())); err != nil {
		return "", errors.Join(err, failure(op, path, parent.Remove(name)))
	}
	return name, nil
}

// setMode sets the read-only attribute of an open file from perm, as
// [os.Chmod] does on Windows.
func setMode(op, path string, file *os.File, perm fs.FileMode) error {
	return failure(op, path, file.Chmod(perm))
}

func (h dirHandle) chmod(op, path string, parts []string, perm fs.FileMode) error {
	return h.withAccess(op, path, parts, windows.FILE_READ_ATTRIBUTES|windows.FILE_WRITE_ATTRIBUTES, func(file *os.File) error {
		return setMode(op, path, file, perm)
	})
}

func (h dirHandle) restrictToOwner(op, path string, parts []string) error {
	return h.withAccess(op, path, parts, windows.READ_CONTROL|windows.WRITE_DAC, func(file *os.File) error {
		return failure(op, path, setOwnerOnlyACL(windows.Handle(file.Fd())))
	})
}

// withAccess opens the regular file of parts, opens it again with access
// through the verified handle, and calls fn with the new handle.
func (h dirHandle) withAccess(op, path string, parts []string, access uint32, fn func(*os.File) error) (err error) {
	file, err := h.openFile(op, path, parts)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, failure(op, path, file.Close())) }()
	handle, err := reopen(windows.Handle(file.Fd()), access)
	if err != nil {
		return failure(op, path, err)
	}
	reopened := os.NewFile(uintptr(handle), file.Name())
	defer func() { err = errors.Join(err, failure(op, path, reopened.Close())) }()
	return fn(reopened)
}

// reopen opens the file of handle again with access, through the Win32
// ReOpenFile function, which golang.org/x/sys/windows does not wrap. The new
// handle refers to the same file, so no path is resolved again.
func reopen(handle windows.Handle, access uint32) (windows.Handle, error) {
	proc := windows.NewLazySystemDLL("kernel32.dll").NewProc("ReOpenFile")
	share := windows.FILE_SHARE_READ | windows.FILE_SHARE_WRITE | windows.FILE_SHARE_DELETE
	r, _, err := proc.Call(uintptr(handle), uintptr(access), uintptr(share), 0)
	if windows.Handle(r) == windows.InvalidHandle {
		return windows.InvalidHandle, fmt.Errorf("ReOpenFile: %w", err)
	}
	return windows.Handle(r), nil
}

// setOwnerOnlyACL gives a file a protected access list that lets only the
// current user read it, as `icacls <file> /inheritance:r /grant:r <user>:R`
// does in core/ssh.py.
func setOwnerOnlyACL(handle windows.Handle) error {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		return fmt.Errorf("GetTokenUser: %w", err)
	}
	acl, err := windows.ACLFromEntries([]windows.EXPLICIT_ACCESS{{
		AccessPermissions: windows.FILE_GENERIC_READ,
		AccessMode:        windows.SET_ACCESS,
		Inheritance:       windows.NO_INHERITANCE,
		Trustee: windows.TRUSTEE{
			TrusteeForm:  windows.TRUSTEE_IS_SID,
			TrusteeType:  windows.TRUSTEE_IS_USER,
			TrusteeValue: windows.TrusteeValueFromSID(user.User.Sid),
		},
	}}, nil)
	if err != nil {
		return fmt.Errorf("SetEntriesInAcl: %w", err)
	}
	err = windows.SetSecurityInfo(handle, windows.SE_FILE_OBJECT,
		windows.DACL_SECURITY_INFORMATION|windows.PROTECTED_DACL_SECURITY_INFORMATION, nil, nil, acl, nil)
	if err != nil {
		return fmt.Errorf("SetSecurityInfo: %w", err)
	}
	return nil
}

func (h dirHandle) remove(op, path string, parts []string) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleOpen)
	if IsReason(err, ReasonNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, parent.close()) }()
	if err := checkLeaf(op, path, parent.root, leaf); err != nil {
		return err
	}
	return absentIsDone(op, path, parent.root.Remove(leaf))
}

func (h dirHandle) removeAll(op, path string, parts []string) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleOpen)
	if IsReason(err, ReasonNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, parent.close()) }()
	entry, err := parent.root.Lstat(leaf)
	if err != nil {
		return absentIsDone(op, path, err)
	}
	if isLink(entry) {
		return &Error{Op: op, Path: path, Reason: ReasonSymlink}
	}
	// [os.Root.RemoveAll] removes a link inside the tree and never follows it.
	return failure(op, path, parent.root.RemoveAll(leaf))
}
