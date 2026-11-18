package securefile

import (
	"path/filepath"
	"testing"
)

// realTempDir returns a new temporary directory with each link resolved. On
// macOS the temporary directory is below a link, and on Windows its path
// can hold short names.
func realTempDir(t *testing.T) string {
	t.Helper()
	root, err := Resolve(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func wantResolve(t *testing.T, path, want string) {
	t.Helper()
	got, err := Resolve(path)
	if err != nil {
		t.Fatalf("Resolve(%q) = %v", path, err)
	}
	if got != want {
		t.Errorf("Resolve(%q) = %q, want %q", path, got, want)
	}
}

func TestResolveKeepsAResolvedPath(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "a")
	wantResolve(t, filepath.Join(root, "a"), filepath.Join(root, "a"))
}

func TestResolveMakesARelativePathAbsolute(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "a")
	t.Chdir(root)
	wantResolve(t, "a", filepath.Join(root, "a"))
	wantResolve(t, ".", root)
}

func TestResolveKeepsAMissingTail(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "a")
	wantResolve(t, filepath.Join(root, "a", "missing", "deeper"), filepath.Join(root, "a", "missing", "deeper"))
	sep := string(filepath.Separator)
	// filepath.Join would remove the ".." part before Resolve reads it.
	wantResolve(t, root+sep+"missing"+sep+".."+sep+"a", filepath.Join(root, "a"))
}
