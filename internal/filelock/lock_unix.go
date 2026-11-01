//go:build linux || darwin

package filelock

import (
	"errors"
	"os"

	"golang.org/x/sys/unix"
)

func tryLock(file *os.File, mode Mode) error {
	how := unix.LOCK_EX | unix.LOCK_NB
	if mode == Shared {
		how = unix.LOCK_SH | unix.LOCK_NB
	}
	return flock(file, how)
}

func unlock(file *os.File) error {
	return flock(file, unix.LOCK_UN)
}

// flock calls flock on the descriptor of file while the file holds it.
func flock(file *os.File, how int) error {
	raw, err := file.SyscallConn()
	if err != nil {
		return failure(file, err)
	}
	var lockErr error
	err = raw.Control(func(fd uintptr) {
		for {
			lockErr = unix.Flock(int(fd), how)
			if !errors.Is(lockErr, unix.EINTR) {
				return
			}
		}
	})
	if errors.Is(lockErr, unix.EWOULDBLOCK) {
		return ErrBusy
	}
	return failure(file, errors.Join(err, lockErr))
}
