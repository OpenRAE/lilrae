package architecture

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"slices"
)

// Check checks the working tree that holds dir against its model. It returns
// an error when the check cannot run, and a report with findings when the code
// or the model breaks a rule.
func Check(ctx context.Context, dir string) (report Report, err error) {
	top, root, err := openRepository(ctx, dir)
	if err != nil {
		return Report{}, err
	}
	defer func() { err = errors.Join(err, closeRoot(root)) }()
	m, err := loadModel(root)
	if err != nil {
		return Report{}, err
	}
	repo, err := scanRepository(ctx, top, root, m.Vendored)
	if err != nil {
		return Report{}, err
	}
	return Report{Findings: checkCode(m, repo)}, nil
}

// loadModel reads and decodes the model of the working tree.
func loadModel(root *os.Root) (*Model, error) {
	data, err := root.ReadFile(ModelPath)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, errNoModel
	}
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", ModelPath, err)
	}
	if len(data) == 0 {
		return nil, fmt.Errorf("%s is empty", ModelPath)
	}
	return parseModel(data)
}

func closeRoot(root *os.Root) error {
	if err := root.Close(); err != nil {
		return fmt.Errorf("close the working tree: %w", err)
	}
	return nil
}

// checkCode returns the findings of the model and of the code against it.
func checkCode(m *Model, repo *repository) []Finding {
	findings := m.validate()
	dirs := repo.packages()
	findings = append(findings, checkPackages(m, repo, dirs)...)
	for _, f := range repo.files {
		if c := m.owner(f.dir); c != nil {
			findings = append(findings, checkImports(m, repo, c, f, dirs)...)
		}
	}
	return findings
}

// checkPackages returns the findings of the package assignment and of the
// public packages. dirs are the package directories of the repository.
func checkPackages(m *Model, repo *repository, dirs []string) []Finding {
	var findings []Finding
	for _, dir := range dirs {
		if m.owner(dir) == nil {
			findings = append(findings, m.finding(RuleUnassignedPackage, dir,
				fmt.Sprintf("the package %s is in no component", quote(dir))))
		}
		if repo.importable(dir) && !internalPath(dir) && !slices.Contains(m.Public, dir) {
			findings = append(findings, m.finding(RuleUndeclaredPublic, dir,
				fmt.Sprintf("the package %s can be imported, but it is not under internal/ and not public", quote(dir))))
		}
	}
	for i := range m.Components {
		c := &m.Components[i]
		for _, p := range c.Packages {
			if !slices.Contains(dirs, p) {
				findings = append(findings, m.finding(RuleStalePackage, m.componentLocation(i),
					fmt.Sprintf("the package %s of %q has no Go file", quote(p), c.Name)))
			}
		}
	}
	return findings
}

// checkImports returns the findings of the imports of a file of component c.
// dirs are the package directories of the repository.
func checkImports(m *Model, repo *repository, c *Component, f goFile, dirs []string) []Finding {
	var findings []Finding
	for _, spec := range f.imports {
		location := fmt.Sprintf("%s:%d", f.path, spec.line)
		resolved := repo.resolve(f.module, spec.path)
		switch resolved.kind {
		case importStandard:
		case importUnresolved:
			findings = append(findings, m.finding(RuleUnresolvedImport, location,
				fmt.Sprintf("the import %s resolves to no first-party package, standard library package, or required module", quote(spec.path))))
		case importFirstParty:
			target := m.owner(resolved.dir)
			if !slices.Contains(dirs, resolved.dir) {
				findings = append(findings, m.finding(RuleUnresolvedImport, location,
					fmt.Sprintf("the import %s names a first-party package that has no Go file", quote(spec.path))))
			} else if target != nil && !mayUse(c, target.Name, f.test) {
				findings = append(findings, m.finding(RuleForbiddenImport, location,
					fmt.Sprintf("the import %s is in %q, which %q does not use", quote(spec.path), target.Name, c.Name)))
			}
		case importModule:
			if !mayImportModule(c, resolved.module, f.test) {
				findings = append(findings, m.finding(RuleForbiddenModule, location,
					fmt.Sprintf("the import %s is in the module %s, which %q may not import", quote(spec.path), quote(resolved.module), c.Name)))
			}
		}
	}
	return findings
}

// mayUse reports whether component c can import a package of component name.
// A test file can also use the test uses.
func mayUse(c *Component, name string, test bool) bool {
	return name == c.Name || slices.Contains(c.Uses, name) || test && slices.Contains(c.TestUses, name)
}

// mayImportModule reports whether component c can import the module mod. A
// test file can also import the test modules.
func mayImportModule(c *Component, mod string, test bool) bool {
	return slices.Contains(c.Modules, mod) || test && slices.Contains(c.TestModules, mod)
}
