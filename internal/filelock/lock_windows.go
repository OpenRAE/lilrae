//go:build windows

package filelock

import (
	"errors"
	"fmt"
	"os"

	"golang.org/x/sys/windows"
)

func tryLock(file *os.File, mode Mode) error {
	if mode == Shared {
		return fmt.Errorf("filelock: %s: a shared lock on Windows: %w", file.Name(), errors.ErrUnsupported)
	}
	err := control(file, func(handle windows.Handle) error {
		return windows.LockFileEx(handle, windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, new(windows.Overlapped))
	})
	if errors.Is(err, windows.ERROR_LOCK_VIOLATION) {
		return ErrBusy
	}
	return failure(file, err)
}

func unlock(file *os.File) error {
	return failure(file, control(file, func(handle windows.Handle) error {
		return windows.UnlockFileEx(handle, 0, 1, 0, new(windows.Overlapped))
	}))
}

// control calls fn with the handle of file while the file holds it. A zero
// Overlapped value names byte 0.
func control(file *os.File, fn func(windows.Handle) error) error {
	raw, err := file.SyscallConn()
	if err != nil {
		return fmt.Errorf("take the handle: %w", err)
	}
	var callErr error
	err = raw.Control(func(fd uintptr) {
		callErr = fn(windows.Handle(fd))
	})
	return errors.Join(err, callErr)
}
