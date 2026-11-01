// Package golayout applies the rules of the go command to the paths of a
// source tree: the paths that the go command ignores, and the module that
// holds a directory.
//
// Paths are slash-separated and relative to the root of the tree, as Git and
// [io/fs] write them.
package golayout

import (
	"errors"
	"fmt"
	"io/fs"
	"path"
	"strings"
)

// Ignored reports whether the go command ignores the file name: an element of
// its path begins with a dot or an underscore, or one of its directories is
// named testdata.
func Ignored(name string) bool {
	elems := strings.Split(name, "/")
	for i, elem := range elems {
		if strings.HasPrefix(elem, ".") || strings.HasPrefix(elem, "_") {
			return true
		}
		if elem == "testdata" && i < len(elems)-1 {
			return true
		}
	}
	return false
}

// ModuleDir returns the directory of the nearest go.mod file at or above the
// directory dir of fsys. It reports false when there is none.
func ModuleDir(fsys fs.FS, dir string) (module string, ok bool, err error) {
	for current := dir; ; current = path.Dir(current) {
		_, err = fs.Stat(fsys, path.Join(current, "go.mod"))
		if err == nil {
			return current, true, nil
		}
		if !errors.Is(err, fs.ErrNotExist) {
			return "", false, fmt.Errorf("look for the go.mod of %s: %w", dir, err)
		}
		if current == "." {
			return "", false, nil
		}
	}
}
