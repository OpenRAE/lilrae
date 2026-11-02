package mutation

import (
	"errors"
	"fmt"
	"io/fs"
	"testing"
	"testing/fstest"
)

// denialFS injects a read failure at one module discovery boundary.
type denialFS struct {
	fs.FS

	denied string
}

func (f denialFS) Open(name string) (fs.File, error) {
	if name == f.denied {
		return nil, fs.ErrPermission
	}
	file, err := f.FS.Open(name)
	if err != nil {
		return nil, fmt.Errorf("open fixture filesystem: %w", err)
	}
	return file, nil
}

// TestModuleDiscoveryFailsClosed checks that a failed directory walk or
// module probe cannot silently omit a module from mutation verification.
func TestModuleDiscoveryFailsClosed(t *testing.T) {
	for _, denied := range []string{".", "sub/go.mod"} {
		t.Run(denied, func(t *testing.T) {
			tree := denialFS{
				FS:     fstest.MapFS{"sub/input.txt": {}},
				denied: denied,
			}
			exclusions, err := exclusionsIn(tree, ".")
			if !errors.Is(err, fs.ErrPermission) || exclusions != nil {
				t.Fatalf("module discovery returned %v, %v; want no exclusions and a permission error", exclusions, err)
			}
		})
	}
}
