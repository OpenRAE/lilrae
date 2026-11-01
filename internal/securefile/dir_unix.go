//go:build linux || darwin

package securefile

import (
	"errors"
	"io/fs"
	"os"

	"golang.org/x/sys/unix"
)

// dirHandle is an open directory. Its [*os.File] keeps the descriptor valid
// while a walk duplicates it, and it refuses each use after a close, so that
// no operation reaches a descriptor number that a later open reuses.
type dirHandle struct{ f *os.File }

func openDirHandle(path string) (dirHandle, error) {
	fd, err := ignoringEINTR2(func() (int, error) {
		return unix.Open(path, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_CLOEXEC, 0)
	})
	if err != nil {
		return dirHandle{}, &Error{Op: "open dir", Path: path, Reason: ReasonBaseDirUnavailable, Err: err}
	}
	return dirHandle{f: os.NewFile(uintptr(fd), path)}, nil
}

func (h dirHandle) close() error {
	return failure("close dir", ".", h.f.Close())
}

// dup returns a new descriptor of the directory. The caller closes it.
func (h dirHandle) dup(op, path string) (int, error) {
	raw, err := h.f.SyscallConn()
	if err != nil {
		return 0, failure(op, path, err)
	}
	var fd int
	var dupErr error
	err = raw.Control(func(sysfd uintptr) {
		fd, dupErr = unix.FcntlInt(sysfd, unix.F_DUPFD_CLOEXEC, 0)
	})
	return fd, failure(op, path, errors.Join(err, dupErr))
}

// walk opens the directories dirs below h one at a time, without following a
// link, and returns a descriptor of the last one, or a new descriptor of h
// when dirs is empty. The caller closes it. After an error, the descriptor
// is 0 and the caller must not use it.
func (h dirHandle) walk(op, path string, dirs []string, rule dirRule) (int, error) {
	fd, err := h.dup(op, path)
	if err != nil {
		return 0, err
	}
	for _, name := range dirs {
		next, err := openDir(op, path, fd, name, rule)
		if err != nil {
			return 0, errors.Join(err, closeFd(op, path, fd))
		}
		if err := closeFd(op, path, fd); err != nil {
			return 0, errors.Join(err, closeFd(op, path, next))
		}
		fd = next
	}
	return fd, nil
}

// walkParent walks to the parent of the last component of parts and returns
// it with the name of the last component.
func (h dirHandle) walkParent(op, path string, parts []string, rule dirRule) (parent int, leaf string, err error) {
	parent, err = h.walk(op, path, parts[:len(parts)-1], rule)
	return parent, parts[len(parts)-1], err
}

// closeFd closes a descriptor that a walk opened.
func closeFd(op, path string, fd int) error {
	return failure(op, path, unix.Close(fd))
}

// openDir opens the directory name under parent without following a link,
// with the rule of the walk.
func openDir(op, path string, parent int, name string, rule dirRule) (int, error) {
	flags := unix.O_RDONLY | unix.O_DIRECTORY | unix.O_NOFOLLOW | unix.O_CLOEXEC
	if rule == ruleSearch {
		flags = searchFlag | unix.O_DIRECTORY | unix.O_NOFOLLOW | unix.O_CLOEXEC
	}
	fd, err := openat(parent, name, flags, 0)
	if errors.Is(err, unix.ENOENT) && rule >= ruleCreate {
		err = mkdirat(parent, name, privateDirMode)
		if err == nil || errors.Is(err, unix.EEXIST) {
			fd, err = openat(parent, name, flags, 0)
		}
	}
	if err != nil {
		return 0, componentError(op, path, parent, name, err)
	}
	if rule >= ruleRestrict {
		if err := restrictDir(op, path, fd, groupOrOtherWrite, rule.requiresOwner()); err != nil {
			return 0, errors.Join(err, closeFd(op, path, fd))
		}
	}
	return fd, nil
}

// requiresOwner reports whether the rule demands that the caller owns each
// directory, also when no mode bit needs clearing.
func (r dirRule) requiresOwner() bool {
	return r == rulePrivate
}

// componentError reports why name could not be opened under parent.
func componentError(op, path string, parent int, name string, err error) error {
	var st unix.Stat_t
	isLink := lstatat(parent, name, &st) == nil && st.Mode&unix.S_IFMT == unix.S_IFLNK
	return &Error{Op: op, Path: path, Reason: openReason(err, isLink), Err: err}
}

// restrictDir clears the forbidden mode bits of an open directory, or
// refuses it.
func restrictDir(op, path string, fd int, forbidden uint32, owned bool) error {
	var st unix.Stat_t
	if err := fstat(fd, &st); err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	mode := statMode(&st) & 0o7777
	want, ok := restrictedMode(mode, st.Uid, os.Geteuid(), forbidden, owned)
	if !ok {
		return &Error{Op: op, Path: path, Reason: ReasonNotPrivate}
	}
	if want == mode {
		return nil
	}
	if err := fchmod(fd, want); err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonNotPrivate, Err: err}
	}
	if err := fstat(fd, &st); err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if statMode(&st)&forbidden != 0 {
		return &Error{Op: op, Path: path, Reason: ReasonNotPrivate}
	}
	return nil
}

// restrictedMode returns mode without the forbidden bits, and false when the
// rule refuses the directory: clearing bits needs ownership, and owned
// demands ownership also when no bit needs clearing.
func restrictedMode(mode, owner uint32, euid int, forbidden uint32, owned bool) (uint32, bool) {
	if (owned || mode&forbidden != 0) && int(owner) != euid {
		return 0, false
	}
	return mode &^ forbidden, true
}

func (h dirHandle) openFile(op, path string, parts []string) (file *os.File, err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleSearch)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, closeFd(op, path, parent)) }()
	// O_NONBLOCK keeps a FIFO from blocking the open.
	fd, err := openat(parent, leaf, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, componentError(op, path, parent, leaf, err)
	}
	if err := checkRegular(op, path, fd); err != nil {
		return nil, errors.Join(err, closeFd(op, path, fd))
	}
	return os.NewFile(uintptr(fd), path), nil
}

// checkRegular refuses an open file that is not a regular file, and it
// clears the O_NONBLOCK flag of the open.
func checkRegular(op, path string, fd int) error {
	var st unix.Stat_t
	if err := fstat(fd, &st); err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if st.Mode&unix.S_IFMT != unix.S_IFREG {
		return &Error{Op: op, Path: path, Reason: ReasonNotRegularFile}
	}
	return failure(op, path, unix.SetNonblock(fd, false))
}

func (h dirHandle) readDirNames(op, path string, parts []string) (names []string, err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleSearch)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, closeFd(op, path, parent)) }()
	d, err := openDir(op, path, parent, leaf, ruleOpen)
	if err != nil {
		return nil, err
	}
	dir := os.NewFile(uintptr(d), path)
	defer func() { err = errors.Join(err, failure(op, path, dir.Close())) }()
	names, err = dir.Readdirnames(-1)
	return names, failure(op, path, err)
}

func (h dirHandle) subdir(op, path string, parts []string, rule dirRule) (dirHandle, error) {
	fd, err := h.walk(op, path, parts, rule)
	if err != nil {
		return dirHandle{}, err
	}
	if rule == rulePrivate {
		if err := restrictDir(op, path, fd, groupOrOtherAccess, true); err != nil {
			return dirHandle{}, errors.Join(err, closeFd(op, path, fd))
		}
	}
	return dirHandle{f: os.NewFile(uintptr(fd), path)}, nil
}

func (h dirHandle) createOnce(op, path string, parts []string, data []byte) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleCreate)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeFd(op, path, parent)) }()
	name, err := writeTemp(op, path, parent, leaf, data, privateFileMode)
	if err != nil {
		return err
	}
	// linkat publishes the complete file and fails when the name exists.
	published := linkat(parent, name, parent, leaf)
	removed := unlinkat(parent, name, 0)
	return failure(op, path, errors.Join(published, removed, fsync(parent)))
}

// replace walks with rule. Under ruleRestrict it also applies the private
// rules to the parent of the leaf, unless the parent is the trusted
// directory, which never changes.
func (h dirHandle) replace(op, path string, parts []string, data []byte, perm fs.FileMode, rule dirRule) error {
	parent, leaf, err := h.walkParent(op, path, parts, rule)
	if err != nil {
		return err
	}
	err = replaceIn(op, path, parent, leaf, data, perm, rule == ruleRestrict && len(parts) > 1)
	return errors.Join(err, closeFd(op, path, parent))
}

// replaceIn replaces leaf under parent. privateParent applies the private
// rules to parent first.
func replaceIn(op, path string, parent int, leaf string, data []byte, perm fs.FileMode, privateParent bool) error {
	if privateParent {
		if err := restrictDir(op, path, parent, groupOrOtherAccess, true); err != nil {
			return err
		}
	}
	if err := checkLeaf(op, path, parent, leaf); err != nil {
		return err
	}
	return publish(op, path, parent, leaf, data, perm)
}

// publish writes a temporary file beside leaf and renames it onto leaf.
// renameat replaces the entry and never follows it, so a link that appears at
// leaf after the check is replaced.
func publish(op, path string, parent int, leaf string, data []byte, perm fs.FileMode) error {
	name, err := writeTemp(op, path, parent, leaf, data, perm)
	if err != nil {
		return err
	}
	if err := renameat(parent, name, parent, leaf); err != nil {
		return failure(op, path, errors.Join(err, unlinkat(parent, name, 0)))
	}
	return failure(op, path, fsync(parent))
}

// checkLeaf refuses an existing leaf that is a link or not a regular file.
func checkLeaf(op, path string, parent int, leaf string) error {
	var st unix.Stat_t
	err := lstatat(parent, leaf, &st)
	if errors.Is(err, unix.ENOENT) {
		return nil
	}
	if err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if st.Mode&unix.S_IFMT == unix.S_IFLNK {
		return &Error{Op: op, Path: path, Reason: ReasonSymlink}
	}
	if st.Mode&unix.S_IFMT != unix.S_IFREG {
		return &Error{Op: op, Path: path, Reason: ReasonNotRegularFile}
	}
	return nil
}

// writeTemp writes data to a new temporary file beside leaf, gives it the
// mode perm, syncs it, and returns its name. It removes the file after a
// failure.
func writeTemp(op, path string, parent int, leaf string, data []byte, perm fs.FileMode) (string, error) {
	name := tempName(leaf)
	fd, err := openat(parent, name, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, uint32(privateFileMode))
	if err != nil {
		return "", &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	file := os.NewFile(uintptr(fd), name)
	if err := errors.Join(fill(op, path, file, data, perm), failure(op, path, file.Close())); err != nil {
		return "", errors.Join(err, failure(op, path, unlinkat(parent, name, 0)))
	}
	return name, nil
}

// setMode sets the mode of an open file and checks that the file system kept
// it.
func setMode(op, path string, file *os.File, perm fs.FileMode) error {
	if err := file.Chmod(perm); err != nil {
		return failure(op, path, err)
	}
	info, err := file.Stat()
	if err != nil {
		return failure(op, path, err)
	}
	if info.Mode().Perm() != perm {
		return &Error{Op: op, Path: path, Reason: ReasonModeNotKept}
	}
	return nil
}

func (h dirHandle) chmod(op, path string, parts []string, perm fs.FileMode) (err error) {
	file, err := h.openFile(op, path, parts)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, failure(op, path, file.Close())) }()
	return setMode(op, path, file, perm)
}

func (h dirHandle) restrictToOwner(op, path string, parts []string) error {
	return h.chmod(op, path, parts, privateFileMode)
}

func (h dirHandle) remove(op, path string, parts []string) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleOpen)
	if IsReason(err, ReasonNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeFd(op, path, parent)) }()
	if err := checkLeaf(op, path, parent, leaf); err != nil {
		return err
	}
	if err := absentIsDone(op, path, unlinkat(parent, leaf, 0)); err != nil {
		return err
	}
	return failure(op, path, fsync(parent))
}

func (h dirHandle) removeAll(op, path string, parts []string) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleOpen)
	if IsReason(err, ReasonNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeFd(op, path, parent)) }()
	var st unix.Stat_t
	if err := lstatat(parent, leaf, &st); err != nil {
		return absentIsDone(op, path, err)
	}
	if st.Mode&unix.S_IFMT == unix.S_IFLNK {
		return &Error{Op: op, Path: path, Reason: ReasonSymlink}
	}
	return removeEntry(op, path, parent, leaf, st.Mode&unix.S_IFMT == unix.S_IFDIR)
}

// removeEntry removes the entry name under dir, and a directory with all
// that it holds. It never follows a link.
func removeEntry(op, path string, dir int, name string, isDir bool) error {
	flags := 0
	if isDir {
		if err := removeContent(op, path, dir, name); err != nil {
			return err
		}
		flags = unix.AT_REMOVEDIR
	}
	return absentIsDone(op, path, unlinkat(dir, name, flags))
}

// removeContent removes each entry of the directory name under parent.
func removeContent(op, path string, parent int, name string) (err error) {
	d, err := openDir(op, path, parent, name, ruleOpen)
	if err != nil {
		return err
	}
	dir := os.NewFile(uintptr(d), name)
	defer func() { err = errors.Join(err, failure(op, path, dir.Close())) }()
	entries, err := dir.Readdirnames(-1)
	if err != nil {
		return failure(op, path, err)
	}
	for _, entry := range entries {
		var st unix.Stat_t
		if err := lstatat(d, entry, &st); err != nil {
			return absentIsDone(op, path, err)
		}
		if err := removeEntry(op, path, d, entry, st.Mode&unix.S_IFMT == unix.S_IFDIR); err != nil {
			return err
		}
	}
	return nil
}

// The system calls below call again after EINTR, as the os package does: the
// runtime sends signals that can interrupt a call on a network or FUSE file
// system.

func openat(dir int, name string, flags int, mode uint32) (int, error) {
	return ignoringEINTR2(func() (int, error) { return unix.Openat(dir, name, flags, mode) })
}

func mkdirat(dir int, name string, mode uint32) error {
	return ignoringEINTR(func() error { return unix.Mkdirat(dir, name, mode) })
}

// lstatat reads the status of the entry name under dir and does not follow
// a link.
func lstatat(dir int, name string, st *unix.Stat_t) error {
	return ignoringEINTR(func() error { return unix.Fstatat(dir, name, st, unix.AT_SYMLINK_NOFOLLOW) })
}

func fstat(fd int, st *unix.Stat_t) error {
	return ignoringEINTR(func() error { return unix.Fstat(fd, st) })
}

func fchmod(fd int, mode uint32) error {
	return ignoringEINTR(func() error { return unix.Fchmod(fd, mode) })
}

func linkat(oldDir int, oldName string, newDir int, newName string) error {
	return ignoringEINTR(func() error { return unix.Linkat(oldDir, oldName, newDir, newName, 0) })
}

func renameat(oldDir int, oldName string, newDir int, newName string) error {
	return ignoringEINTR(func() error { return unix.Renameat(oldDir, oldName, newDir, newName) })
}

func unlinkat(dir int, name string, flags int) error {
	return ignoringEINTR(func() error { return unix.Unlinkat(dir, name, flags) })
}

func fsync(fd int) error {
	return ignoringEINTR(func() error { return unix.Fsync(fd) })
}

func ignoringEINTR(fn func() error) error {
	for {
		if err := fn(); !errors.Is(err, unix.EINTR) {
			return err
		}
	}
}

func ignoringEINTR2(fn func() (int, error)) (int, error) {
	for {
		fd, err := fn()
		if !errors.Is(err, unix.EINTR) {
			return fd, err
		}
	}
}
