// Package filelock takes shared and exclusive locks on an open file, with
// the lock primitive of the Python callers, so that a Go lock and a Python
// lock on one file exclude each other.
//
// On Linux and macOS a lock is a flock lock. On Windows it locks byte 0 for
// a length of 1, as core/lifecycle_guard.py does with msvcrt.locking, and a
// shared lock is not supported. Reentrancy, the scope, and the order of the
// locks stay with each caller.
package filelock

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/OpenRAE/lilrae/internal/wait"
)

// Mode is the mode of a lock.
type Mode int

// The modes of a lock. Shared locks exclude only an exclusive lock.
const (
	Shared Mode = iota
	Exclusive
)

// ErrBusy reports that another holder keeps a conflicting lock.
var ErrBusy = errors.New("filelock: another holder keeps a conflicting lock")

// pollInterval is the time between two attempts of Lock: 20 ms.
const pollInterval time.Duration = 20e6

// TryLock takes the lock of mode on file at once, or returns ErrBusy.
func TryLock(file *os.File, mode Mode) error {
	return tryLock(file, mode)
}

// Lock takes the lock of mode on file, and waits until it gets the lock,
// the timeout passes, or ctx ends. A blocking system call cannot stop at a
// deadline, so Lock calls TryLock every 20 ms. After the timeout it returns
// an error that matches [wait.ErrTimeout].
func Lock(ctx context.Context, file *os.File, mode Mode, timeout time.Duration) error {
	var lockErr error
	_, err := wait.Until(ctx, timeout, pollInterval, func(context.Context) bool {
		lockErr = tryLock(file, mode)
		return !errors.Is(lockErr, ErrBusy)
	})
	if err != nil {
		return fmt.Errorf("filelock: lock %s: %w", file.Name(), err)
	}
	return lockErr
}

// Unlock releases the lock on file.
func Unlock(file *os.File) error {
	return unlock(file)
}

// failure adds the name of the file to an error from the system.
func failure(file *os.File, err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("filelock: %s: %w", file.Name(), err)
}
