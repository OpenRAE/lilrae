//go:build windows

package filelock

import (
	"errors"
	"testing"
)

func TestASharedLockIsNotSupportedOnWindows(t *testing.T) {
	first, _ := openTwice(t)
	if err := TryLock(first, Shared); !errors.Is(err, errors.ErrUnsupported) {
		t.Fatalf("TryLock(Shared) = %v, want an error that matches errors.ErrUnsupported", err)
	}
}
