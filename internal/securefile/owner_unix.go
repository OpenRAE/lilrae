//go:build linux || darwin

package securefile

import (
	"errors"
	"fmt"
	"os"

	"golang.org/x/sys/unix"
)

func (h dirHandle) checkWriteOwner() error {
	return h.checkDirectoryAccess(func(fd int) error {
		return checkUnixAccess(fd, groupOrOtherWrite, false)
	})
}

func (h dirHandle) checkDirectoryAccess(check func(int) error) (err error) {
	const op = "check directory owner access"
	fd, err := h.dup(op, ".")
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeFd(op, ".", fd)) }()
	if checkErr := check(fd); checkErr != nil {
		return &Error{Op: op, Path: ".", Reason: ReasonNotPrivate, Err: checkErr}
	}
	return nil
}

func checkOwnedAccess(file *os.File, private bool) error {
	forbidden := uint32(groupOrOtherWrite)
	if private {
		forbidden = groupOrOtherAccess
	}
	return checkUnixAccess(int(file.Fd()), forbidden, true)
}

func checkUnixAccess(fd int, forbidden uint32, singleLink bool) error {
	var st unix.Stat_t
	if err := fstat(fd, &st); err != nil {
		return fmt.Errorf("stat owner access: %w", err)
	}
	if int64(st.Uid) != int64(os.Geteuid()) || statMode(&st)&forbidden != 0 {
		return errors.New("unsafe ownership or permissions")
	}
	if singleLink && st.Nlink != 1 {
		return errors.New("file has more than one link")
	}
	return checkExtendedACL(fd, forbidden == groupOrOtherAccess)
}
