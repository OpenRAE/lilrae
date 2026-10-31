// Package gittest creates Git repositories for tests.
package gittest

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// Repo is a Git repository in a temporary directory of a test.
type Repo struct {
	tb testing.TB
	// Dir is the root of the working tree.
	Dir string
}

// New returns an empty repository on the branch main. Commits use a fixed
// identity and no signature, so they do not depend on the Git configuration
// of the host.
func New(tb testing.TB) *Repo {
	tb.Helper()
	r := &Repo{tb: tb, Dir: tb.TempDir()}
	r.Git("init", "--quiet", "--initial-branch=main")
	r.Git("config", "user.name", "Fixture")
	r.Git("config", "user.email", "fixture@example.invalid")
	r.Git("config", "commit.gpgsign", "false")
	return r
}

// Commit writes files, where an empty content deletes the file, commits all
// changes, and returns the full name of the new commit.
func (r *Repo) Commit(files map[string]string) string {
	r.tb.Helper()
	for name, content := range files {
		path := filepath.Join(r.Dir, filepath.FromSlash(name))
		if content == "" {
			if err := os.Remove(path); err != nil {
				r.tb.Fatal(err)
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
			r.tb.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
			r.tb.Fatal(err)
		}
	}
	r.Git("add", "--all")
	r.Git("commit", "--quiet", "--allow-empty", "--message=fixture")
	return r.Git("rev-parse", "HEAD")
}

// Git runs git in the repository and returns its output without surrounding
// space. It fails the test when git fails.
func (r *Repo) Git(args ...string) string {
	r.tb.Helper()
	cmd := exec.CommandContext(r.tb.Context(), "git", args...) //nolint:gosec // G204: tests pass fixed arguments, and no shell runs.
	cmd.Dir = r.Dir
	out, err := cmd.CombinedOutput()
	if err != nil {
		r.tb.Fatalf("git %s: %v\n%s", strings.Join(args, " "), err, out)
	}
	return strings.TrimSpace(string(out))
}
