//go:build linux || darwin

package projectstate

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"syscall"
	"testing"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

func mode(t *testing.T, path string) fs.FileMode {
	t.Helper()
	info, err := os.Lstat(path)
	if err != nil {
		t.Fatal(err)
	}
	return info.Mode().Perm()
}

func symlink(t *testing.T, target, name string) {
	t.Helper()
	if err := os.Symlink(target, name); err != nil {
		t.Fatal(err)
	}
}

func TestTheStateLayoutIsPrivate(t *testing.T) {
	root := newProject(t)
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatal(err)
	}
	for path, want := range map[string]fs.FileMode{
		StateDir:     0o700,
		LifecycleDir: 0o700,
		LockFile:     0o600,
	} {
		if got := mode(t, filepath.Join(root, path)); got != want {
			t.Errorf("the mode of %s = %v, want %v", path, got, want)
		}
	}
}

func TestAnExistingLockFileBecomesPrivate(t *testing.T) {
	root := newProject(t)
	lock := filepath.Join(root, LockFile)
	writeFile(t, lock, "")
	if err := os.Chmod(lock, 0o644); err != nil { //nolint:gosec // G302: the test gives the lock file a public mode to check that the lock makes it private.
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatal(err)
	}
	if got := mode(t, lock); got != 0o600 {
		t.Errorf("the mode of the lock file = %v, want 0600", got)
	}
}

func TestTheLockFileKeepsItsContent(t *testing.T) {
	root := newProject(t)
	lock := filepath.Join(root, LockFile)
	writeFile(t, lock, "kept")
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatal(err)
	}
	if data, err := fs.ReadFile(os.DirFS(root), LockFile); err != nil || string(data) != "kept" {
		t.Errorf("the lock file holds %q, %v, want kept", data, err)
	}
}

func TestALinkedStateDirectoryIsUnavailable(t *testing.T) {
	root := newProject(t)
	outside := resolvedTempDir(t)
	symlink(t, outside, filepath.Join(root, StateDir))
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrUnavailable, textUnavailable)
	if exists(t, filepath.Join(outside, "lifecycle")) {
		t.Error("the lock followed the link")
	}
}

func TestALinkedLockFileIsUnavailable(t *testing.T) {
	root := newProject(t)
	mkdir(t, filepath.Join(root, LifecycleDir))
	target := filepath.Join(resolvedTempDir(t), "target")
	symlink(t, target, filepath.Join(root, LockFile))
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrUnavailable, textUnavailable)
	if exists(t, target) {
		t.Error("the lock created the target of the link")
	}
}

func TestAFIFOAtTheLockPathIsUnavailable(t *testing.T) {
	root := newProject(t)
	mkdir(t, filepath.Join(root, LifecycleDir))
	if err := syscall.Mkfifo(filepath.Join(root, LockFile), 0o600); err != nil {
		t.Fatal(err)
	}
	err := Mutate(t.Context(), root, "", mustNotRun(t))
	wantRefusal(t, err, ErrUnavailable, textUnavailable)
	if !securefile.IsReason(err, securefile.ReasonNotRegularFile) {
		t.Errorf("Mutate() = %v, want the cause not_regular_file", err)
	}
}

func TestALinkedFenceIsUnavailable(t *testing.T) {
	root := newProject(t)
	mkdir(t, filepath.Join(root, LifecycleDir))
	symlink(t, filepath.Join(root, "missing"), filepath.Join(root, TrialFence))
	err := Mutate(t.Context(), root, "", mustNotRun(t))
	wantRefusal(t, err, ErrUnavailable, textTrialUnavailable)
	if !securefile.IsReason(err, securefile.ReasonSymlink) {
		t.Errorf("Mutate() = %v, want the cause symlink", err)
	}
}

func TestOpenProjectRootRefusesALinkedRoot(t *testing.T) {
	target := newProject(t)
	link := filepath.Join(resolvedTempDir(t), "link")
	symlink(t, target, link)
	dir, err := OpenProjectRoot(link)
	if err == nil {
		t.Cleanup(func() {
			if closeErr := dir.Close(); closeErr != nil {
				t.Error(closeErr)
			}
		})
	}
	if !securefile.IsReason(err, securefile.ReasonSymlink) {
		t.Fatalf("OpenProjectRoot() of a link = %v, want the reason symlink", err)
	}
}

func TestMutateResolvesALinkedProjectPath(t *testing.T) {
	root := newProject(t)
	link := filepath.Join(resolvedTempDir(t), "link")
	symlink(t, root, link)
	var got string
	if err := Mutate(t.Context(), link, "", func(_ context.Context, r string) error {
		got = r
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if got != root {
		t.Errorf("Mutate gave the root %q, want %q", got, root)
	}
}

func TestProjectRootFollowsALinkWithAMissingTarget(t *testing.T) {
	first, second := newProject(t), newProject(t)
	alias := filepath.Join(first, "alias")
	symlink(t, filepath.Join(second, "missing"), alias)
	got, err := ProjectRoot(alias)
	if err != nil {
		t.Fatal(err)
	}
	if got != second {
		t.Errorf("ProjectRoot() through a link to a missing path = %q, want the owner of the target %q", got, second)
	}
}

func TestObserversShareAndExcludeAMutation(t *testing.T) {
	root := newProject(t)
	err := Observe(root, func(string) error {
		if err := Observe(root, func(string) error { return nil }); err != nil {
			t.Errorf("a second Observe() = %v, want nil", err)
		}
		wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatalf("Mutate() after the observers = %v, want nil", err)
	}
}

func TestAMutationExcludesAnObserver(t *testing.T) {
	root := newProject(t)
	err := Mutate(t.Context(), root, "", func(context.Context, string) error {
		err := Observe(root, func(string) error {
			t.Error("the callback ran after a refusal")
			return nil
		})
		wantRefusal(t, err, ErrBusy, textBusy)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestObserveAnchorsToTheConfigOwnerAndReturnsTheCallbackError(t *testing.T) {
	root := newProject(t)
	nested := filepath.Join(root, "nested")
	mkdir(t, nested)
	want := errors.New("callback failed")
	var got string
	err := Observe(nested, func(r string) error {
		got = r
		return want
	})
	if !errors.Is(err, want) {
		t.Fatalf("Observe() = %v, want %v", err, want)
	}
	if got != root {
		t.Errorf("Observe gave the root %q, want %q", got, root)
	}
}
