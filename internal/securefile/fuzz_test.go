package securefile

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"testing"
)

// FuzzCheckPath compares the lexical rules with [filepath.Localize], which
// accepts the same names, except a name that is only a dot.
func FuzzCheckPath(f *testing.F) {
	for _, seed := range []string{"a", "a/b", "", ".", "..", "/a", "a//b", "a/", "a\x00b", `a\b`, "C:a", "a/NUL", "a/\xff", "a/./b"} {
		f.Add(seed)
	}
	lexical := []Reason{ReasonNULByte, ReasonEmptyComponent, ReasonNotRelative, ReasonDotComponent, ReasonTraversal, ReasonInvalidName}
	f.Fuzz(func(t *testing.T, name string) {
		err := CheckPath(name)
		_, localErr := filepath.Localize(name)
		if want := name != "." && localErr == nil; (err == nil) != want {
			t.Fatalf("CheckPath(%q) = %v, want accepted = %v", name, err, want)
		}
		if e, ok := errors.AsType[*Error](err); err != nil && (!ok || !slices.Contains(lexical, e.Reason)) {
			t.Fatalf("CheckPath(%q) = %v, want a lexical reason", name, err)
		}
	})
}

// FuzzOpen compares Open with a model that walks the name with Lstat: a link
// at any component is symlink, an absent component or one that is not a
// directory is not_found, and a leaf that is not a regular file is
// not_regular_file.
func FuzzOpen(f *testing.F) {
	root, d := fuzzTree(f)
	for _, seed := range []string{"a/b/f", "la/b/f", "a/lb/f", "a/b/lf", "a/b", "a/b/d", "dangling", "up/a", "abs/b/f", "missing", "a/b/f/x", "", "/a", "a//b", "a/../a/b/f"} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, name string) {
		file, err := d.Open(name)
		want, ok := modelOpen(root, name)
		switch {
		case ok && err != nil:
			t.Fatalf("Open(%q) = %v, want the file", name, err)
		case ok:
			checkSameFile(t, root, name, file)
		case err == nil:
			t.Fatalf("Open(%q) succeeded, want %s", name, want)
		case !IsReason(err, want):
			t.Fatalf("Open(%q) = %v, want %s", name, err, want)
		}
	})
}

// fuzzTree makes a tree with links of each kind and returns a Dir of it.
func fuzzTree(f *testing.F) (string, *Dir) {
	f.Helper()
	root := f.TempDir()
	writeFile(f, root, "a/b/f", "data")
	mkdir(f, root, "a/b/d")
	symlink(f, root, "b", "a/lb")
	symlink(f, root, "a", "la")
	symlink(f, root, "f", "a/b/lf")
	symlink(f, root, "missing", "dangling")
	symlink(f, root, "..", "up")
	symlink(f, root, filepath.Join(root, "a"), "abs")
	d, err := OpenDir(root)
	if err != nil {
		f.Fatal(err)
	}
	closeOnCleanup(f, d)
	return root, d
}

// checkSameFile fails the test when file is not the entry name below root.
func checkSameFile(t *testing.T, root, name string, file *os.File) {
	t.Helper()
	opened, statErr := file.Stat()
	entry, lstatErr := os.Lstat(filepath.Join(root, filepath.FromSlash(name)))
	if err := errors.Join(statErr, lstatErr, file.Close()); err != nil {
		t.Fatal(err)
	}
	if !os.SameFile(opened, entry) {
		t.Fatalf("Open(%q) opened another file", name)
	}
}

// modelOpen returns the reason that Open must report for name below root, or
// true when Open must open the file.
func modelOpen(root, name string) (Reason, bool) {
	if e, ok := errors.AsType[*Error](CheckPath(name)); ok {
		return e.Reason, false
	}
	parts := strings.Split(name, "/")
	path := root
	for i, part := range parts {
		path = filepath.Join(path, part)
		info, err := os.Lstat(path)
		switch {
		case errors.Is(err, fs.ErrNotExist) || errors.Is(err, syscall.ENOTDIR):
			return ReasonNotFound, false
		case err != nil:
			return ReasonOpenFailed, false
		case info.Mode()&fs.ModeSymlink != 0:
			return ReasonSymlink, false
		case i < len(parts)-1 && !info.IsDir():
			return ReasonNotFound, false
		case i == len(parts)-1 && !info.Mode().IsRegular():
			return ReasonNotRegularFile, false
		}
	}
	return "", true
}
