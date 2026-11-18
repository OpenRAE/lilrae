package projectstate

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"
)

// holderEnv names the project root that a holder process locks. The test
// binary runs as a holder when the variable is set.
const holderEnv = "LILRAE_PROJECTSTATE_TEST_HOLDER"

func TestMain(m *testing.M) {
	if root := os.Getenv(holderEnv); root != "" {
		if err := holdLock(root); err != nil {
			panic(err)
		}
		return
	}
	m.Run()
}

// holdLock holds the mutation lock of root, writes locked, and keeps the
// lock until its standard input closes.
func holdLock(root string) error {
	return Mutate(context.Background(), root, "", func(context.Context, string) error {
		if _, err := os.Stdout.WriteString("locked\n"); err != nil {
			return fmt.Errorf("write: %w", err)
		}
		if _, err := io.Copy(io.Discard, os.Stdin); err != nil {
			return fmt.Errorf("read: %w", err)
		}
		return nil
	})
}

// startHolder starts cmd, waits until it prints locked, and returns a
// function that closes its standard input and waits for it. The test stops
// the holder at its end.
func startHolder(t *testing.T, cmd *exec.Cmd) (release func() error) {
	t.Helper()
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
	release = sync.OnceValue(func() error { return errors.Join(stdin.Close(), cmd.Wait()) })
	t.Cleanup(func() {
		if releaseErr := release(); releaseErr != nil {
			t.Logf("the holder ended with %v", releaseErr)
		}
	})
	line, err := bufio.NewReader(stdout).ReadString('\n')
	if err != nil || strings.TrimSpace(line) != "locked" {
		t.Fatalf("the holder printed %q, %v, want locked", line, err)
	}
	return release
}

// releaseTimeout bounds the wait for the system to release the lock of a
// killed process. Linux and macOS release it at once. Windows releases it
// after a time that depends on the system resources.
const releaseTimeout = 10 * time.Second

func TestAKilledHolderReleasesTheLock(t *testing.T) {
	root := newProject(t)
	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=^$") //nolint:gosec // G204: the test binary runs itself as a holder.
	cmd.Env = append(os.Environ(), holderEnv+"="+root)
	release := startHolder(t, cmd)
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
	if err := cmd.Process.Kill(); err != nil {
		t.Fatal(err)
	}
	if err := release(); err == nil {
		t.Fatal("the killed holder exited with no error")
	}
	deadline := time.Now().Add(releaseTimeout)
	for err := Mutate(t.Context(), root, "", noop); err != nil; err = Mutate(t.Context(), root, "", noop) {
		if !errors.Is(err, ErrBusy) || time.Now().After(deadline) {
			t.Fatalf("Mutate() after the holder died = %v, want nil", err)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

// pythonLock takes the lifecycle lock of core/lifecycle_guard.py on the
// project root of its first argument, or prints busy. It opens the lock file
// as the Python release does, and on Windows it writes the NUL byte to an
// empty file before the lock. A failure of the open or the write is not
// busy, so it ends the program with an error. With the argument hold, it
// keeps the lock until its standard input closes.
const pythonLock = `import os, sys
path = os.path.join(sys.argv[1], ".aptl", "lifecycle", ".lock")
os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
if os.name == "nt":
    import msvcrt
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)
try:
    if os.name == "nt":
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

func pythonCommand(ctx context.Context, t *testing.T, args ...string) *exec.Cmd {
	t.Helper()
	return exec.CommandContext(ctx, python(t), append([]string{"-c", pythonLock}, args...)...) //nolint:gosec // G204: the interpreter from PATH runs a fixed program on a directory of the test.
}

func runPython(ctx context.Context, t *testing.T, root string) string {
	t.Helper()
	out, err := pythonCommand(ctx, t, root).Output()
	if err != nil {
		t.Fatalf("the Python lock failed: %v: %s", err, out)
	}
	return strings.TrimSpace(string(out))
}

func TestAGoLockExcludesAPythonLock(t *testing.T) {
	// A new project: Go creates the lock file.
	root := newProject(t)
	err := Mutate(t.Context(), root, "", func(ctx context.Context, _ string) error {
		if got := runPython(ctx, t, root); got != "busy" {
			t.Errorf("Python while Go holds the lock printed %q, want busy", got)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := runPython(t.Context(), t, root); got != "locked" {
		t.Errorf("Python after the Go release printed %q, want locked", got)
	}
}

func TestAPythonLockExcludesAGoLock(t *testing.T) {
	// A new project: Python creates the lock file.
	root := newProject(t)
	release := startHolder(t, pythonCommand(t.Context(), t, root, "hold"))
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
	if err := release(); err != nil {
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatalf("Mutate() after the Python release = %v, want nil", err)
	}
}
