//go:build windows

package securefile

import (
	"context"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveResolvesAJunction(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "real/sub")
	junction, target := filepath.Join(root, "junction"), filepath.Join(root, "real")
	out, err := exec.CommandContext(context.Background(), "cmd", "/c", "mklink", "/J", junction, target).CombinedOutput() //nolint:gosec // G204: fixed program; the arguments are paths in the temporary directory of the test.
	if err != nil {
		t.Fatalf("mklink /J: %v: %s", err, out)
	}
	want, err := Resolve(filepath.Join(root, "real", "sub"))
	if err != nil {
		t.Fatal(err)
	}
	wantResolve(t, filepath.Join(junction, "sub"), want)
	wantResolve(t, filepath.Join(junction, "missing"), filepath.Join(filepath.Dir(want), "missing"))
}

func TestResolveFollowsAJunctionWithAMissingTarget(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "b")
	junction, target := filepath.Join(root, "alias"), filepath.Join(root, "b", "missing")
	out, err := exec.CommandContext(context.Background(), "cmd", "/c", "mklink", "/J", junction, target).CombinedOutput() //nolint:gosec // G204: fixed program; the arguments are paths in the temporary directory of the test.
	if err != nil {
		t.Fatalf("mklink /J: %v: %s", err, out)
	}
	wantResolve(t, junction, target)
	wantResolve(t, filepath.Join(junction, "x"), filepath.Join(target, "x"))
}

func TestResolveGivesNoLongPathPrefix(t *testing.T) {
	got, err := Resolve(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if strings.HasPrefix(got, `\\?\`) || !filepath.IsAbs(got) {
		t.Errorf("Resolve() = %q, want an absolute path with no long path prefix", got)
	}
}

func TestTrimLongPrefix(t *testing.T) {
	for in, want := range map[string]string{
		`\\?\C:\a`:           `C:\a`,
		`\\?\UNC\server\s\a`: `\\server\s\a`,
		`C:\a`:               `C:\a`,
	} {
		if got := trimLongPrefix(in); got != want {
			t.Errorf("trimLongPrefix(%q) = %q, want %q", in, got, want)
		}
	}
}
