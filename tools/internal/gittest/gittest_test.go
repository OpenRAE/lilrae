package gittest_test

import (
	"os"
	"path/filepath"
	"testing"

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
