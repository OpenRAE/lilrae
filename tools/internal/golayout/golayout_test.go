package golayout_test

import (
	"errors"
	"io/fs"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

func TestIgnored(t *testing.T) {
	t.Parallel()
	for name, want := range map[string]bool{
		"a/b/c.go":            false,
		"main.go":             false,
		"a/testdata.go":       false,
		"a/testdata":          false,
		"a/my_test.go":        false,
		"a/testdata/c.go":     true,
		"testdata/c.go":       true,
		"a/testdata/b/c.go":   true,
		"a/.hidden/c.go":      true,
		".github/x.go":        true,
		"a/_build/c.go":       true,
		"_tools/c.go":         true,
		"a/.c.go":             true,
		"a/_c.go":             true,
		"a/b_/c.go":           false,
		"a/b.d/c.go":          false,
		"a/notestdata/c.go":   false,
		"a/testdatafile/c.go": false,
	} {
		if got := golayout.Ignored(name); got != want {
			t.Errorf("Ignored(%q) = %t, want %t", name, got, want)
		}
	}
}

func TestModuleDir(t *testing.T) {
	t.Parallel()
	fsys := fstest.MapFS{
		"go.mod":                {},
		"a/b/c.go":              {},
		"tools/go.mod":          {},
		"tools/internal/x/x.go": {},
	}
	for dir, want := range map[string]string{
		".":                ".",
		"a":                ".",
		"a/b":              ".",
		"tools":            "tools",
		"tools/internal/x": "tools",
		"missing/dir":      ".",
	} {
		got, ok, err := golayout.ModuleDir(fsys, dir)
		if err != nil || !ok || got != want {
			t.Errorf("ModuleDir(%q) = %q, %t, %v; want %q, true, nil", dir, got, ok, err, want)
		}
	}
}

func TestModuleDirReportsNoModule(t *testing.T) {
	t.Parallel()
	fsys := fstest.MapFS{"a/b/c.go": {}}
	for _, dir := range []string{".", "a", "a/b"} {
		if got, ok, err := golayout.ModuleDir(fsys, dir); err != nil || ok || got != "" {
			t.Errorf("ModuleDir(%q) = %q, %t, %v; want \"\", false, nil", dir, got, ok, err)
		}
	}
}

// deniedFS fails each Stat with a permission error.
type deniedFS struct{}

func (deniedFS) Open(name string) (fs.File, error) {
	return nil, &fs.PathError{Op: "open", Path: name, Err: fs.ErrPermission}
}

func TestModuleDirReturnsAReadError(t *testing.T) {
	t.Parallel()
	got, ok, err := golayout.ModuleDir(deniedFS{}, "a/b")
	if !errors.Is(err, fs.ErrPermission) || ok || got != "" {
		t.Errorf("ModuleDir() = %q, %t, %v; want \"\", false, and a permission error", got, ok, err)
	}
}
