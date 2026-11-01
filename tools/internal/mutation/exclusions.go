package mutation

import (
	"errors"
	"fmt"
	"go/build"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

// exclusions returns the Gremlins file exclusions of the module in dir.
// Gremlins walks each .go file below dir, but the tests of the module cannot
// cover three kinds of file, so Gremlins would count their mutants as not
// covered:
//
//   - a file of a nested module, which the gate mutates in its own module;
//   - a file below a directory that the go command ignores, such as
//     testdata;
//   - a file that build constraints leave out on the host. The gate runs on
//     each platform of the product, so a host where the file builds checks
//     its mutants.
//
// An exclusion matches the slash-separated path relative to dir, which is
// the path that Gremlins walks.
func exclusions(dir string) ([]string, error) {
	fsys := os.DirFS(dir)
	var rules []string
	err := fs.WalkDir(fsys, ".", func(name string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return fmt.Errorf("walk the module %s: %w", dir, walkErr)
		}
		rule, err := exclusion(fsys, dir, name, d)
		if rule != "" {
			rules = append(rules, rule)
		}
		return err
	})
	if err != nil {
		return nil, fmt.Errorf("find the files that the tests of %s cannot cover: %w", dir, err)
	}
	return rules, nil
}

// exclusion returns the exclusion of the entry name of the module in dir, or
// "" for an entry that the tests of the module can cover. It returns
// [fs.SkipDir] with the exclusion of a directory.
func exclusion(fsys fs.FS, dir, name string, d fs.DirEntry) (string, error) {
	if name == "." {
		return "", nil
	}
	if d.IsDir() {
		nested, err := isModule(fsys, name)
		// The go command ignores each file below an ignored directory.
		if nested || golayout.Ignored(path.Join(name, "file.go")) {
			return "^" + regexp.QuoteMeta(name) + "/", fs.SkipDir
		}
		return "", err
	}
	if path.Ext(name) != ".go" || strings.HasSuffix(name, "_test.go") {
		return "", nil
	}
	match, err := build.Default.MatchFile(filepath.Join(dir, filepath.FromSlash(path.Dir(name))), path.Base(name))
	if err != nil {
		return "", fmt.Errorf("read the build constraints of %s: %w", name, err)
	}
	if match {
		return "", nil
	}
	return "^" + regexp.QuoteMeta(name) + "$", nil
}

// isModule reports whether the directory name of fsys holds a go.mod file.
func isModule(fsys fs.FS, name string) (bool, error) {
	_, err := fs.Stat(fsys, path.Join(name, "go.mod"))
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("look for the go.mod of %s: %w", name, err)
	}
	return true, nil
}
