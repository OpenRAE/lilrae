//go:build windows

package filelock

import (
	"errors"
	"testing"

	"golang.org/x/sys/windows"
)

func TestASharedLockIsNotSupportedOnWindows(t *testing.T) {
	first, _ := openTwice(t)
	if err := TryLock(first, Shared); !errors.Is(err, errors.ErrUnsupported) {
		t.Fatalf("TryLock(Shared) = %v, want an error that matches errors.ErrUnsupported", err)
	}
}

func TestTheWindowsLockCoversOnlyByteZero(t *testing.T) {
	first, second := openTwice(t)
	if err := TryLock(first, Exclusive); err != nil {
		t.Fatal(err)
	}
	if err := control(second, func(handle windows.Handle) error {
		return windows.LockFileEx(handle, windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &windows.Overlapped{Offset: 1})
	}); err != nil {
		t.Fatalf("locking byte 1 beside the byte 0 lock = %v, want nil", err)
	}
	if err := control(second, func(handle windows.Handle) error {
		return windows.UnlockFileEx(handle, 0, 1, 0, &windows.Overlapped{Offset: 1})
	}); err != nil {
		t.Fatal(err)
	}
}
