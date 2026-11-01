package architecture

import (
	"context"
	"errors"
	"fmt"
	"path"
	"slices"
	"strconv"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

// PRConfig describes the check of a pull request.
type PRConfig struct {
	// Repo is a directory in the working tree of the head revision.
	Repo string
	// Base is the base revision of the change.
	Base string
	// Issue is the issue of the branch, or 0 when the branch names no issue.
	Issue int
	// Promotion reports that the head is a protected branch of this
	// repository. Its changes came through pull requests with this check, so
	// the design comparison does not apply.
	Promotion bool
}

// CheckPullRequest checks the whole working tree against its model, and then
// checks the change from the base revision to HEAD against the design record
// of the issue.
func CheckPullRequest(ctx context.Context, cfg PRConfig) (report Report, err error) {
	top, root, err := openRepository(ctx, cfg.Repo)
	if err != nil {
		return Report{}, err
	}
	defer func() { err = errors.Join(err, closeRoot(root)) }()
	head, err := loadModel(root)
	if err != nil {
		return Report{}, err
	}
	repo, err := scanRepository(ctx, top, root, head.Vendored)
	if err != nil {
		return Report{}, err
	}
	findings := checkCode(head, repo)
	if cfg.Promotion {
		return Report{Findings: findings}, nil
	}
	changes, err := modelChangesSince(ctx, top, cfg.Base, head)
	if err != nil {
		return Report{}, err
	}
	changed, err := changedPackages(ctx, top, cfg.Base, head)
	if err != nil {
		return Report{}, err
	}
	if len(changes) == 0 && len(changed) == 0 {
		return Report{Findings: findings}, nil
	}
	if cfg.Issue <= 0 {
		findings = append(findings, head.finding(RuleMissingDesign, "the branch",
			"the change edits Go packages or the model, but the branch names no issue, so it has no design note"))
		return Report{Findings: findings}, nil
	}
	compared, err := compareDesign(ctx, top, head, repo, cfg.Issue, changes, changed)
	if err != nil {
		return Report{}, err
	}
	return Report{Findings: append(findings, compared...)}, nil
}

// changedPackages returns the first-party package directories that the change
// from base to HEAD adds, changes, or removes.
func changedPackages(ctx context.Context, top, base string, m *Model) ([]string, error) {
	baseRev, err := git.ResolveCommit(ctx, top, base)
	if err != nil {
		return nil, err
	}
	headRev, err := git.ResolveCommit(ctx, top, "HEAD")
	if err != nil {
		return nil, err
	}
	files, err := git.ChangedFiles(ctx, top, baseRev, headRev, "*.go")
	if err != nil {
		return nil, err
	}
	var dirs []string
	for _, f := range files {
		dir := path.Dir(f.Path)
		vendored := slices.ContainsFunc(m.Vendored, func(v string) bool { return within(f.Path, v) })
		if golayout.Ignored(f.Path) || vendored || slices.Contains(dirs, dir) {
			continue
		}
		dirs = append(dirs, dir)
	}
	return dirs, nil
}

// compareDesign compares the change with the design record of issue.
func compareDesign(ctx context.Context, top string, m *Model, repo *repository, issue int, changes, changed []string) ([]Finding, error) {
	pattern := "docs/architecture/issue-" + strconv.Itoa(issue) + "-*-design.md"
	notes, err := git.TrackedFiles(ctx, top, pattern)
	if err != nil {
		return nil, err
	}
	switch len(notes) {
	case 0:
		return []Finding{m.finding(RuleMissingDesign, pattern,
			fmt.Sprintf("the change edits Go packages or the model, but issue %d has no tracked design note", issue))}, nil
	case 1:
	default:
		return []Finding{m.finding(RuleInvalidDesign, pattern, fmt.Sprintf("issue %d has %d design notes", issue, len(notes)))}, nil
	}
	data, err := repo.root.ReadFile(notes[0])
	if err != nil {
		return nil, fmt.Errorf("read the design note: %w", err)
	}
	record, err := parseRecord(notes[0], data)
	if errors.Is(err, errNoFrontMatter) {
		return []Finding{m.finding(RuleInvalidDesign, notes[0], err.Error())}, nil
	}
	if err != nil {
		return nil, err
	}
	findings := checkRecord(m, repo, notes[0], record, issue, changes)
	return append(findings, compareCode(m, repo, notes[0], record, changed)...), nil
}

// compareCode compares the changed packages and their imports with a design
// record.
func compareCode(m *Model, repo *repository, name string, r *Record, changed []string) []Finding {
	var findings []Finding
	recorded := map[string]RecordPackage{}
	for _, p := range r.Packages {
		recorded[p.Path] = p
	}
	for _, dir := range changed {
		if _, ok := recorded[dir]; !ok {
			findings = append(findings, m.finding(RuleDesignPackageMissing, name,
				fmt.Sprintf("the change edits the package %s, which the design record does not list", quote(dir))))
		}
	}
	for _, p := range r.Packages {
		imports, testImports, exists := repo.observedImports(p.Path)
		switch {
		case p.Removed && exists:
			findings = append(findings, m.finding(RuleDesignImportsDiffer, name,
				fmt.Sprintf("the design record removes the package %s, but it has Go files", quote(p.Path))))
		case p.Removed:
		case !sameSet(imports, p.Imports) || !sameSet(testImports, p.TestImports):
			findings = append(findings, m.finding(RuleDesignImportsDiffer, name, fmt.Sprintf(
				"the imports of %s are %s and the test imports are %s, but the design record lists %s and %s",
				quote(p.Path), quoteAll(imports), quoteAll(testImports), quoteAll(p.Imports), quoteAll(p.TestImports))))
		}
	}
	return findings
}

// observedImports returns the first-party and module imports of the package in
// dir: those of its other files, and those that only its test files have. An
// external test package that imports its own package does not count. It
// reports whether the package has Go files.
func (r *repository) observedImports(dir string) (imports, testImports []string, exists bool) {
	for _, f := range r.files {
		if f.dir != dir {
			continue
		}
		exists = true
		for _, spec := range f.imports {
			name, ok := r.recordName(f.module, dir, spec.path)
			switch {
			case !ok:
			case f.test:
				testImports = append(testImports, name)
			default:
				imports = append(imports, name)
			}
		}
	}
	return compactSorted(imports), setDifference(testImports, imports), exists
}

// recordName returns the name of an import of the package in dir in a design
// record: the import path of a first-party package, or the path of a module.
// It reports false for a standard library import and for an import of the
// package itself.
func (r *repository) recordName(from *goModule, dir, importPath string) (string, bool) {
	resolved := r.resolve(from, importPath)
	switch resolved.kind {
	case importStandard:
		return "", false
	case importModule:
		return resolved.module, true
	case importFirstParty:
		return importPath, resolved.dir != dir
	case importUnresolved:
	}
	return importPath, true
}

// compactSorted returns the sorted entries without duplicates.
func compactSorted(entries []string) []string {
	out := slices.Clone(entries)
	slices.Sort(out)
	return slices.Compact(out)
}
