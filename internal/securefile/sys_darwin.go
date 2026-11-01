package securefile

import (
	"errors"
	"io/fs"

	"golang.org/x/sys/unix"
)

// searchFlag opens a directory to search it, which needs execute permission
// only (O_SEARCH).
const searchFlag = unix.O_SEARCH

// statMode returns the mode of a file status.
func statMode(st *unix.Stat_t) uint32 {
	return uint32(st.Mode)
}

// chmodLeaf sets the mode of the regular file leaf under parent. It needs no
// access to the content of the file: fchmodat with AT_SYMLINK_NOFOLLOW
// changes the entry itself and follows no link.
func chmodLeaf(op, path string, parent int, leaf string, perm uint32) error {
	var st unix.Stat_t
	if err := lstatat(parent, leaf, &st); err != nil {
		return componentError(op, path, parent, leaf, err)
	}
	if err := regularEntry(op, path, statMode(&st)); err != nil {
		return err
	}
	chmodErr := fchmodat(parent, leaf, perm, unix.AT_SYMLINK_NOFOLLOW)
	var after unix.Stat_t
	statErr := lstatat(parent, leaf, &after)
	return errors.Join(failure(op, path, errors.Join(chmodErr, statErr)), keptPerm(op, path, statPerm(&after), fs.FileMode(perm)))
}
