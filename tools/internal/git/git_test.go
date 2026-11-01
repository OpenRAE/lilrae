package git_test

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

// newRepo returns a repository with two commits: base and head.
func newRepo(t *testing.T) (r *gittest.Repo, base, head string) {
	t.Helper()
	r = gittest.New(t)
	base = r.Commit(map[string]string{
		"a/keep.go": "package a\n",
		"a/edit.go": "package a\n",
		"a/gone.go": "package a\n",
		"a/old.go":  "package a // rename\n",
	})
	r.Git("mv", "a/old.go", "a/renamed.go")
	if err := os.Symlink("keep.go", filepath.Join(r.Dir, "a", "link.go")); err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(r.Dir, "a", "run.sh")
	if err := os.WriteFile(script, []byte("#!/bin/sh\n"), 0o700); err != nil { //nolint:gosec // G306: the script needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}
	head = r.Commit(map[string]string{
		"a/edit.go":    "package a // edited\n",
		"a/new.go":     "package a\n",
		"a/b/deep.txt": "deep\n",
		"other.txt":    "other\n",
		"a/gone.go":    "",
	})
	return r, base, head
}

func TestTopLevelAndResolveCommit(t *testing.T) {
	t.Parallel()
	r, base, head := newRepo(t)
	dir := r.Dir

	top, err := git.TopLevel(t.Context(), filepath.Join(dir, "a", "b"))
	if err != nil || top != dir {
		t.Errorf("TopLevel(%s/a/b) = %q, %v; want %q", dir, top, err, dir)
	}
	for rev, want := range map[string]string{"HEAD": head, "HEAD~1": base, base[:12]: base} {
		if got, err := git.ResolveCommit(t.Context(), dir, rev); err != nil || got != want {
			t.Errorf("ResolveCommit(%q) = %q, %v; want %q", rev, got, err, want)
		}
	}
	for _, rev := range []string{"--output=x", "missing", "HEAD:a/keep.go"} {
		if got, err := git.ResolveCommit(t.Context(), dir, rev); err == nil {
			t.Errorf("ResolveCommit(%q) = %q, want an error: the revision names no commit", rev, got)
		}
	}
}

func TestChangedFiles(t *testing.T) {
	t.Parallel()
	r, base, head := newRepo(t)
	dir := r.Dir
	// git diff would list the files in this order; diff-tree ignores it.
	order := filepath.Join(t.TempDir(), "order")
	if err := os.WriteFile(order, []byte("a/renamed.go\na/edit.go\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	r.Git("config", "diff.orderFile", order)

	got, err := git.ChangedFiles(t.Context(), dir, base, head, "*.go")
	if err != nil {
		t.Fatal(err)
	}

	want := []git.Change{
		{Path: "a/edit.go"},
		{Path: "a/gone.go", Deleted: true},
		{Path: "a/link.go"},
		{Path: "a/new.go"},
		{Path: "a/old.go", Deleted: true},
		{Path: "a/renamed.go"},
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("ChangedFiles(*.go) mismatch (-want +got):\n%s", diff)
	}
}

func TestTrackedFiles(t *testing.T) {
	t.Parallel()
	r, _, _ := newRepo(t)
	if err := os.WriteFile(filepath.Join(r.Dir, "a", "untracked.go"), []byte("package a\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := git.TrackedFiles(t.Context(), r.Dir, "*.go", "other.txt")
	if err != nil {
		t.Fatal(err)
	}

	want := []string{"a/edit.go", "a/keep.go", "a/link.go", "a/new.go", "a/renamed.go", "other.txt"}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("TrackedFiles(*.go, other.txt) mismatch (-want +got):\n%s", diff)
	}
	if _, err := git.TrackedFiles(t.Context(), filepath.Join(r.Dir, "missing")); err == nil {
		t.Error("TrackedFiles(missing directory) returned no error")
	}
}

func TestFiles(t *testing.T) {
	t.Parallel()
	r, _, head := newRepo(t)
	dir := r.Dir

	got, err := git.Files(t.Context(), dir, head, "a")
	if err != nil {
		t.Fatal(err)
	}

	want := []git.Entry{
		{Path: "a/b/deep.txt", Mode: "100644"},
		{Path: "a/edit.go", Mode: "100644"},
		{Path: "a/keep.go", Mode: "100644"},
		{Path: "a/link.go", Mode: "120000"},
		{Path: "a/new.go", Mode: "100644"},
		{Path: "a/renamed.go", Mode: "100644"},
		{Path: "a/run.sh", Mode: "100755"},
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("Files(a) mismatch (-want +got):\n%s", diff)
	}
}

func TestShow(t *testing.T) {
	t.Parallel()
	r, base, head := newRepo(t)
	dir := r.Dir

	got, err := git.Show(t.Context(), dir, head, "a/edit.go")
	if err != nil || string(got) != "package a // edited\n" {
		t.Errorf("Show(head, a/edit.go) = %q, %v; want the head content", got, err)
	}
	if got, err := git.Show(t.Context(), dir, base, "a/new.go"); !errors.Is(err, git.ErrNotExist) {
		t.Errorf("Show(base, a/new.go) = %q, %v; want ErrNotExist", got, err)
	}
	if _, err := git.Show(t.Context(), dir, "0000000000000000000000000000000000000000", "a/edit.go"); err == nil || errors.Is(err, git.ErrNotExist) {
		t.Errorf("Show(missing commit) error = %v, want a git error that is not ErrNotExist", err)
	}
}

func TestRunReportsTheCommandAndItsError(t *testing.T) {
	t.Parallel()
	r, _, _ := newRepo(t)
	dir := r.Dir

	_, err := git.Run(t.Context(), dir, "cat-file", "blob", "HEAD:missing")

	if err == nil || !strings.Contains(err.Error(), "git cat-file blob HEAD:missing") || !strings.Contains(err.Error(), "missing") {
		t.Errorf("Run(cat-file blob HEAD:missing) error = %v, want the command and the git message", err)
	}
}
