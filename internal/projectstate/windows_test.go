//go:build windows

package projectstate

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

func junction(t *testing.T, name, target string) {
	t.Helper()
	out, err := exec.CommandContext(t.Context(), "cmd", "/c", "mklink", "/J", name, target).CombinedOutput() //nolint:gosec // G204: fixed program; the arguments are paths in the temporary directory of the test.
	if err != nil {
		t.Fatalf("mklink /J: %v: %s", err, out)
	}
}

func TestObserveIsBusyAndUnsupportedOnWindows(t *testing.T) {
	root := newProject(t)
	err := Observe(root, func(string) error {
		t.Error("the callback ran after a refusal")
		return nil
	})
	wantRefusal(t, err, ErrBusy, textBusy)
	if !errors.Is(err, errors.ErrUnsupported) {
		t.Errorf("Observe() = %v, want an error that matches errors.ErrUnsupported", err)
	}
}

func TestAJunctionedStateDirectoryIsUnavailable(t *testing.T) {
	root := newProject(t)
	outside := resolvedTempDir(t)
	junction(t, filepath.Join(root, StateDir), outside)
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrUnavailable, textUnavailable)
	if exists(t, filepath.Join(outside, "lifecycle")) {
		t.Error("the lock followed the junction")
	}
}

func TestOpenProjectRootRefusesAJunctionedRoot(t *testing.T) {
	target := newProject(t)
	link := filepath.Join(resolvedTempDir(t), "link")
	junction(t, link, target)
	dir, err := OpenProjectRoot(link)
	if err == nil {
		t.Cleanup(func() {
			if closeErr := dir.Close(); closeErr != nil {
				t.Error(closeErr)
			}
		})
	}
	if !securefile.IsReason(err, securefile.ReasonSymlink) {
		t.Fatalf("OpenProjectRoot() of a junction = %v, want the reason symlink", err)
	}
}

func TestMutateResolvesAJunctionedProjectPath(t *testing.T) {
	root := newProject(t)
	link := filepath.Join(resolvedTempDir(t), "link")
	junction(t, link, root)
	var got string
	if err := Mutate(t.Context(), link, "", func(_ context.Context, r string) error {
		got = r
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if got != root {
		t.Errorf("Mutate gave the root %q, want the junction target %q", got, root)
	}
}

func TestANewLockFileHoldsOneNULByte(t *testing.T) {
	root := newProject(t)
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatal(err)
	}
	data, err := fs.ReadFile(os.DirFS(root), LockFile)
	if err != nil || string(data) != "\x00" {
		t.Errorf("the lock file holds %q, %v, want one NUL byte", data, err)
	}
}
