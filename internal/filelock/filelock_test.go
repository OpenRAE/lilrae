package filelock

import (
	"bufio"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"testing/synctest"
	"time"

	"github.com/OpenRAE/lilrae/internal/wait"
)

// openTwice returns two opens of one new lock file, which hold two locks.
func openTwice(t *testing.T) (first, second *os.File) {
	t.Helper()
	root, err := os.OpenRoot(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := root.Close(); err != nil {
			t.Error(err)
		}
	})
	first = openFile(t, root, os.O_RDWR|os.O_CREATE)
	second = openFile(t, root, os.O_RDWR)
	return first, second
}

func openFile(t *testing.T, root *os.Root, flag int) *os.File {
	t.Helper()
	file, err := root.OpenFile("lock", flag, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := file.Close(); err != nil {
			t.Error(err)
		}
	})
	return file
}

func TestAnExclusiveLockExcludesAnother(t *testing.T) {
	first, second := openTwice(t)
	if err := TryLock(first, Exclusive); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(second, Exclusive); !errors.Is(err, ErrBusy) {
		t.Fatalf("TryLock() of a held lock = %v, want ErrBusy", err)
	}
	if err := Unlock(first); err != nil {
		t.Fatal(err)
	}
	if err := TryLock(second, Exclusive); err != nil {
		t.Fatalf("TryLock() after Unlock = %v, want nil", err)
	}
}

func TestLockWaitsForTheRelease(t *testing.T) {
	first, second := openTwice(t)
	synctest.Test(t, func(t *testing.T) {
		if err := TryLock(first, Exclusive); err != nil {
			t.Fatal(err)
		}
		go func() {
			time.Sleep(100 * time.Millisecond)
			if err := Unlock(first); err != nil {
				t.Error(err)
			}
		}()
		start := time.Now()
		if err := Lock(t.Context(), second, Exclusive, time.Second); err != nil {
			t.Fatalf("Lock() = %v, want nil", err)
		}
		if waited := time.Since(start); waited < 100*time.Millisecond || waited > 120*time.Millisecond {
			t.Errorf("Lock() took %v, want the release after 100ms and one interval at most", waited)
		}
	})
}

func TestLockStopsAtTheTimeout(t *testing.T) {
	first, second := openTwice(t)
	synctest.Test(t, func(t *testing.T) {
		if err := TryLock(first, Exclusive); err != nil {
			t.Fatal(err)
		}
		err := Lock(t.Context(), second, Exclusive, 100*time.Millisecond)
		if !errors.Is(err, wait.ErrTimeout) || !strings.HasPrefix(err.Error(), "filelock: lock ") {
			t.Fatalf("Lock() of a held lock = %v, want an error of the package that matches wait.ErrTimeout", err)
		}
	})
}

func TestLockReturnsAnErrorOtherThanBusyAtOnce(t *testing.T) {
	closed, err := os.CreateTemp(t.TempDir(), "closed")
	if err != nil {
		t.Fatal(err)
	}
	if err := closed.Close(); err != nil {
		t.Fatal(err)
	}
	synctest.Test(t, func(t *testing.T) {
		start := time.Now()
		err := Lock(t.Context(), closed, Exclusive, time.Second)
		if err == nil || errors.Is(err, ErrBusy) || errors.Is(err, wait.ErrTimeout) {
			t.Fatalf("Lock() of a closed file = %v, want its own error", err)
		}
		if waited := time.Since(start); waited != 0 {
			t.Errorf("Lock() of a closed file waited %v, want no wait", waited)
		}
	})
}

// pythonLock takes the lock of core/lifecycle_guard.py on the file of its
// first argument, or prints busy. With the argument hold, it keeps the lock
// until its standard input closes.
const pythonLock = `import os, sys
fd = os.open(sys.argv[1], os.O_RDWR)
try:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("busy", flush=True)
    sys.exit(0)
print("locked", flush=True)
if sys.argv[2:] == ["hold"]:
    sys.stdin.read()
`

// python returns the path of a Python interpreter. CI installs one, so a
// missing interpreter fails the test.
func python(t *testing.T) string {
	t.Helper()
	names := []string{"python3", "python"}
	if runtime.GOOS == "windows" {
		// The Microsoft Store can install a python3 alias that runs no program.
		names = []string{"python", "python3"}
	}
	for _, name := range names {
		if path, err := exec.LookPath(name); err == nil {
			return path
		}
	}
	t.Fatal("the test needs a Python interpreter on PATH")
	return ""
}

func runPython(t *testing.T, args ...string) string {
	t.Helper()
	out, err := exec.CommandContext(t.Context(), python(t), append([]string{"-c", pythonLock}, args...)...).Output() //nolint:gosec // G204: the interpreter from PATH runs a fixed program on a file of the test.
	if err != nil {
		t.Fatal(err)
	}
	return strings.TrimSpace(string(out))
}

func TestAGoLockAndAPythonLockExcludeEachOther(t *testing.T) {
	first, second := openTwice(t)
	path := filepath.Join(filepath.Dir(first.Name()), "lock")

	// A Python holder keeps the Go lock out.
	cmd := exec.CommandContext(t.Context(), python(t), "-c", pythonLock, path, "hold") //nolint:gosec // G204: the interpreter from PATH runs a fixed program on a file of the test.
	stdin, err := cmd.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if startErr := cmd.Start(); startErr != nil {
		t.Fatal(startErr)
	}
	line, err := bufio.NewReader(stdout).ReadString('\n')
	if err != nil || strings.TrimSpace(line) != "locked" {
		t.Fatalf("the Python holder printed %q, %v, want locked", line, err)
	}
	if err := TryLock(second, Exclusive); !errors.Is(err, ErrBusy) {
		t.Errorf("TryLock() while Python holds the lock = %v, want ErrBusy", err)
	}
	if err := errors.Join(stdin.Close(), cmd.Wait()); err != nil {
		t.Fatal(err)
	}

	// A Go holder keeps the Python lock out.
	if err := TryLock(second, Exclusive); err != nil {
		t.Fatalf("TryLock() after the Python holder ended = %v, want nil", err)
	}
	if got := runPython(t, path); got != "busy" {
		t.Errorf("Python while Go holds the lock printed %q, want busy", got)
	}
	if err := Unlock(second); err != nil {
		t.Fatal(err)
	}
	if got := runPython(t, path); got != "locked" {
		t.Errorf("Python after Unlock printed %q, want locked", got)
	}
}
