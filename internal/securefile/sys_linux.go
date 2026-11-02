package securefile

import (
	"errors"
	"io/fs"
	"strconv"

	"golang.org/x/sys/unix"
)

// searchFlag opens a directory to search it, which needs execute permission
// only (O_PATH).
const searchFlag = unix.O_PATH

// statMode returns the mode of a file status.
func statMode(st *unix.Stat_t) uint32 {
	return st.Mode
}

// chmodLeaf sets the mode of the regular file leaf under parent. It needs no
// access to the content of the file and follows no link: it opens the file
// itself with O_PATH, checks it, and changes the mode of that open file
// through /proc/self/fd, as GNU libc does for fchmodat without fchmodat2.
func chmodLeaf(op, path string, parent int, leaf string, perm uint32) (err error) {
	fd, err := openat(parent, leaf, unix.O_PATH|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if err != nil {
		return componentError(op, path, parent, leaf, err)
	}
	defer func() { err = errors.Join(err, closeFd(op, path, fd)) }()
	var st unix.Stat_t
	if err := fstat(fd, &st); err != nil {
		return &Error{Op: op, Path: path, Reason: ReasonOpenFailed, Err: err}
	}
	if err := regularEntry(op, path, statMode(&st)); err != nil {
		return err
	}
	chmodErr := fchmodat(unix.AT_FDCWD, "/proc/self/fd/"+strconv.Itoa(fd), perm, 0)
	var after unix.Stat_t
	statErr := fstat(fd, &after)
	return errors.Join(failure(op, path, errors.Join(chmodErr, statErr)), keptPerm(op, path, statPerm(&after), fs.FileMode(perm)))
}
