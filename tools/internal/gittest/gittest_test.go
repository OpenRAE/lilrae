package gittest_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

func TestCommitWritesAndDeletesFiles(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)

	first := r.Commit(map[string]string{"a/b.txt": "b\n", "c.txt": "c\n"})
	second := r.Commit(map[string]string{"c.txt": ""})

	if got := r.Git("rev-parse", "HEAD~1"); got != first {
		t.Errorf("HEAD~1 = %q, want the first commit %q", got, first)
	}
	if got := r.Git("rev-parse", "HEAD"); got != second || len(second) != 40 {
		t.Errorf("HEAD = %q, want the second commit %q as a full name", got, second)
	}
	if got := r.Git("show", "HEAD:a/b.txt"); got != "b" {
		t.Errorf("a/b.txt = %q, want %q", got, "b")
	}
	if _, err := os.Stat(filepath.Join(r.Dir, "c.txt")); !os.IsNotExist(err) {
		t.Errorf("c.txt exists after the second commit (error %v), want it deleted", err)
	}
	if got := r.Git("log", "-1", "--format=%an %ae %G?"); got != "Fixture fixture@example.invalid N" {
		t.Errorf("commit identity = %q, want the fixed identity without a signature", got)
	}
}

// TestRepoIgnoresTheHostConfiguration gives the host a Git configuration
// whose hooks fail and whose commits are signed with a missing key. The
// fixture commits still work, and so does a command that the code under test
// runs in the repository with the host configuration.
func TestRepoIgnoresTheHostConfiguration(t *testing.T) {
	hooks := t.TempDir()
	for _, hook := range []string{"pre-commit", "commit-msg", "post-checkout"} {
		if err := os.WriteFile(filepath.Join(hooks, hook), []byte("#!/bin/sh\nexit 1\n"), 0o700); err != nil { //nolint:gosec // G306: a hook needs the owner execute bit; 0700 gives no access to other users.
			t.Fatal(err)
		}
	}
	global := filepath.Join(t.TempDir(), "gitconfig")
	config := "[core]\n\thooksPath = " + hooks + "\n[commit]\n\tgpgsign = true\n[user]\n\tsigningkey = " + filepath.Join(hooks, "missing") + "\n[gpg]\n\tformat = ssh\n"
	if err := os.WriteFile(global, []byte(config), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("GIT_CONFIG_GLOBAL", global)
	r := gittest.New(t)

	r.Commit(map[string]string{"a.txt": "a\n"})

	tree := filepath.Join(t.TempDir(), "tree")
	if _, err := git.Run(t.Context(), r.Dir, "worktree", "add", "--detach", "--quiet", tree, "HEAD"); err != nil {
		t.Errorf("git worktree add with the host configuration: %v", err)
	}
}
