//go:build linux || darwin

package filelock

import (
	"errors"
	"testing"
)

func TestSharedLocksExcludeOnlyAnExclusiveLock(t *testing.T) {
	first, second := openTwice(t)
	if err := TryLock(first, Shared); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(second, Shared); err != nil {
		t.Fatalf("TryLock(Shared) beside a shared lock = %v, want nil", err)
	}
	if err := Unlock(second); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(second, Exclusive); !errors.Is(err, ErrBusy) {
		t.Fatalf("TryLock(Exclusive) beside a shared lock = %v, want ErrBusy", err)
	}
	if err := Unlock(first); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(first, Exclusive); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(second, Shared); !errors.Is(err, ErrBusy) {
		t.Fatalf("TryLock(Shared) beside an exclusive lock = %v, want ErrBusy", err)
	}
}
