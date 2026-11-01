package architecture

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The public API cannot make a rename fail after the temporary file exists, so
// this test calls replaceFile.
func TestReplaceFileLeavesNoTemporaryFileAfterAFailure(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "target"), 0o750); err != nil {
		t.Fatal(err)
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if closeErr := root.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	})

	err = replaceFile(root, "target", []byte("new"), 0o600)

	if err == nil || !strings.HasPrefix(err.Error(), "replace target: ") || strings.Contains(err.Error(), "remove") {
		t.Errorf("replaceFile(onto a directory) error = %v, want only the error of the rename", err)
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Name() != "target" {
		t.Errorf("the directory holds %d entries after the failure, want only the target", len(entries))
	}
}
