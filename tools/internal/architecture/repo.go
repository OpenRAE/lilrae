package architecture

import (
	"context"
	"errors"
	"fmt"
	"go/parser"
	"go/token"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"golang.org/x/mod/modfile"
	"golang.org/x/mod/module"

	"github.com/OpenRAE/lilrae/tools/internal/git"
)

// repository is the first-party Go code of a working tree.
type repository struct {
	root *os.Root
	// modules are the first-party modules, longest directory first.
	modules []*goModule
	// byPath are the first-party modules, longest module path first.
	byPath []*goModule
	// files are the first-party Go files, by path.
	files []goFile
}

// goModule is a first-party module.
type goModule struct {
	dir  string
	path string
	// requires are the required module paths, longest first.
	requires []string
}

// goFile is a first-party Go file.
type goFile struct {
	path    string
	dir     string
	test    bool
	pkgName string
	module  *goModule
	imports []importSpec
}

// importSpec is one import of a file.
type importSpec struct {
	path string
	line int
}

// importKind is the kind of an import.
type importKind int

const (
	importUnresolved importKind = iota
	importStandard
	importFirstParty
	importModule
)

// resolvedImport is an import resolved to a first-party package directory or
// to a module.
type resolvedImport struct {
	kind importKind
	// dir is the package directory of a first-party import.
	dir string
	// module is the module path of a third-party import.
	module string
}

// openRepository opens the working tree that holds dir.
func openRepository(ctx context.Context, dir string) (string, *os.Root, error) {
	top, err := git.TopLevel(ctx, dir)
	if err != nil {
		return "", nil, err
	}
	root, err := os.OpenRoot(top)
	if err != nil {
		return "", nil, fmt.Errorf("open the working tree: %w", err)
	}
	return top, root, nil
}

// treePath returns the path of file in the working tree at top. A relative
// file is relative to top.
func treePath(top, file string) (string, error) {
	if !filepath.IsAbs(file) {
		file = filepath.Join(top, file)
	}
	rel, err := filepath.Rel(top, file)
	if err != nil || !filepath.IsLocal(rel) {
		return "", fmt.Errorf("the file %s is not in the working tree", quote(file))
	}
	return rel, nil
}

// scanRepository reads the tracked first-party Go files and go.mod files of
// the working tree at top. Vendored directories and the paths that the go
// command ignores are not first party.
func scanRepository(ctx context.Context, top string, root *os.Root, vendored []string) (*repository, error) {
	out, err := git.Run(ctx, top, "ls-files", "-z", "--", "*.go", "go.mod", "*/go.mod")
	if err != nil {
		return nil, err
	}
	repo := &repository{root: root}
	var goFiles []string
	for name := range strings.SplitSeq(string(out), "\x00") {
		if name == "" || ignored(name) || slices.ContainsFunc(vendored, func(v string) bool { return within(name, v) }) {
			continue
		}
		if path.Base(name) == "go.mod" {
			mod, err := repo.readModule(name)
			if err != nil {
				return nil, err
			}
			repo.modules = append(repo.modules, mod)
			continue
		}
		goFiles = append(goFiles, name)
	}
	slices.SortFunc(repo.modules, func(a, b *goModule) int { return len(b.dir) - len(a.dir) })
	repo.byPath = slices.Clone(repo.modules)
	slices.SortFunc(repo.byPath, func(a, b *goModule) int { return len(b.path) - len(a.path) })
	for _, name := range goFiles {
		f, err := repo.readFile(name)
		if err != nil {
			return nil, err
		}
		repo.files = append(repo.files, f)
	}
	return repo, nil
}

// readModule parses a go.mod file.
func (r *repository) readModule(name string) (*goModule, error) {
	data, err := r.root.ReadFile(filepath.FromSlash(name))
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", name, err)
	}
	f, err := modfile.ParseLax(name, data, nil)
	if err != nil || f.Module == nil {
		return nil, fmt.Errorf("%s: cannot parse the module file", name)
	}
	mod := &goModule{dir: path.Dir(name), path: f.Module.Mod.Path}
	for _, req := range f.Require {
		mod.requires = append(mod.requires, req.Mod.Path)
	}
	slices.SortFunc(mod.requires, func(a, b string) int { return len(b) - len(a) })
	return mod, nil
}

// readFile reads the package name and the imports of a Go file.
func (r *repository) readFile(name string) (goFile, error) {
	data, err := r.root.ReadFile(filepath.FromSlash(name))
	if err != nil {
		return goFile{}, fmt.Errorf("read %s: %w", name, err)
	}
	fset := token.NewFileSet()
	parsed, err := parser.ParseFile(fset, name, data, parser.ImportsOnly|parser.SkipObjectResolution)
	if err != nil {
		// The parser message can quote source text, so it is not shown.
		return goFile{}, fmt.Errorf("%s: cannot parse the Go file", name)
	}
	f := goFile{
		path:    name,
		dir:     path.Dir(name),
		test:    strings.HasSuffix(name, "_test.go"),
		pkgName: parsed.Name.Name,
		module:  r.moduleOf(name),
	}
	for _, spec := range parsed.Imports {
		value, err := strconv.Unquote(spec.Path.Value)
		if err != nil {
			return goFile{}, fmt.Errorf("%s: cannot read an import path", name)
		}
		f.imports = append(f.imports, importSpec{path: value, line: fset.Position(spec.Pos()).Line})
	}
	return f, nil
}

// moduleOf returns the first-party module that holds a file, or nil.
func (r *repository) moduleOf(name string) *goModule {
	for _, mod := range r.modules {
		if within(name, mod.dir) {
			return mod
		}
	}
	return nil
}

// resolve resolves an import path of a file in module from. A path that is
// not a valid import path resolves to nothing. With a nil module, as for the
// imports of a design record, a path that is not first party and not in the
// standard library resolves to nothing.
func (r *repository) resolve(from *goModule, importPath string) resolvedImport {
	if module.CheckImportPath(importPath) != nil {
		return resolvedImport{kind: importUnresolved}
	}
	for _, mod := range r.byPath {
		if rest, ok := underPath(importPath, mod.path); ok {
			return resolvedImport{kind: importFirstParty, dir: path.Join(mod.dir, rest)}
		}
	}
	if first, _, _ := strings.Cut(importPath, "/"); !strings.Contains(first, ".") {
		return resolvedImport{kind: importStandard}
	}
	if from != nil {
		for _, req := range from.requires {
			if _, ok := underPath(importPath, req); ok {
				return resolvedImport{kind: importModule, module: req}
			}
		}
	}
	return resolvedImport{kind: importUnresolved}
}

// packages returns the package directories of the first-party Go files.
func (r *repository) packages() []string {
	var dirs []string
	for _, f := range r.files {
		if !slices.Contains(dirs, f.dir) {
			dirs = append(dirs, f.dir)
		}
	}
	return dirs
}

// importable reports whether the package in dir can be imported: it has a
// file that is not a test file and is not a command.
func (r *repository) importable(dir string) bool {
	return slices.ContainsFunc(r.files, func(f goFile) bool { return f.dir == dir && !f.test && f.pkgName != "main" })
}

// underPath reports whether importPath is modulePath or below it, and returns
// the rest of the path.
func underPath(importPath, modulePath string) (string, bool) {
	if importPath == modulePath {
		return "", true
	}
	rest, ok := strings.CutPrefix(importPath, modulePath+"/")
	return rest, ok
}

// ignored reports whether the go command ignores a repository path: a
// directory or file name in it begins with a dot or an underscore, or a
// directory is named testdata.
func ignored(name string) bool {
	for part := range strings.SplitSeq(name, "/") {
		if strings.HasPrefix(part, ".") || strings.HasPrefix(part, "_") {
			return true
		}
	}
	return slices.Contains(strings.Split(path.Dir(name), "/"), "testdata")
}

// errNoModel reports a working tree without a model.
var errNoModel = errors.New("the working tree has no architecture/model.yaml")
