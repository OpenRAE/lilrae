package architecture

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"maps"
	"path/filepath"
	"regexp"
	"slices"
	"strings"

	"golang.org/x/mod/module"

	"github.com/OpenRAE/lilrae/tools/internal/git"
)

// Record is the design record in the front matter of a design note.
type Record struct {
	Design       int             `yaml:"design"`
	Issue        int             `yaml:"issue"`
	Packages     []RecordPackage `yaml:"packages"`
	ModelChanges []string        `yaml:"model_changes"`
}

// RecordPackage is a new, changed, or removed package of a design record.
type RecordPackage struct {
	Path        string   `yaml:"path"`
	Component   string   `yaml:"component"`
	Imports     []string `yaml:"imports"`
	TestImports []string `yaml:"test_imports"`
	Removed     bool     `yaml:"removed"`
}

// componentChange starts the model change of a component.
const componentChange = "component:"

var changePattern = regexp.MustCompile(`^(layers|public|rules|vendored|component:[a-z][a-z0-9-]*(\.(layer|responsibility|packages|uses|modules|test_uses|test_modules))?)$`)

// errNoFrontMatter reports a design note without a design record.
var errNoFrontMatter = errors.New("the design note has no design front matter")

// parseRecord decodes the design record in the front matter of a design note.
func parseRecord(name string, note []byte) (*Record, error) {
	body, ok := bytes.CutPrefix(note, []byte("---\n"))
	if !ok {
		return nil, errNoFrontMatter
	}
	front, _, ok := bytes.Cut(body, []byte("\n---\n"))
	if !ok {
		return nil, errNoFrontMatter
	}
	var r Record
	if _, err := decodeStrict(front, &r); err != nil {
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	if r.Design != 1 {
		return nil, fmt.Errorf("%s: the design record version must be 1", name)
	}
	return &r, nil
}

// CheckDesign checks the design note file of the working tree that holds dir
// against the model of the working tree. It checks the model changes of the
// record against the model of the base revision. The code does not need to
// exist.
func CheckDesign(ctx context.Context, dir, base, file string) (report Report, err error) {
	top, root, err := openRepository(ctx, dir)
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
	changes, err := modelChangesSince(ctx, top, base, head)
	if err != nil {
		return Report{}, err
	}
	rel, err := treePath(top, file)
	if err != nil {
		return Report{}, err
	}
	note, err := root.ReadFile(rel)
	if err != nil {
		return Report{}, fmt.Errorf("read the design note: %w", err)
	}
	name := filepath.ToSlash(rel)
	record, err := parseRecord(name, note)
	if errors.Is(err, errNoFrontMatter) {
		return Report{Findings: []Finding{head.finding(RuleInvalidDesign, name, err.Error())}}, nil
	}
	if err != nil {
		return Report{}, err
	}
	findings := head.validate()
	findings = append(findings, checkRecord(head, repo, name, record, record.Issue, changes)...)
	return Report{Findings: findings}, nil
}

// modelChangesSince returns the changed parts of the model since base. A base
// revision without a model has the empty model.
func modelChangesSince(ctx context.Context, top, base string, head *Model) ([]string, error) {
	rev, err := git.ResolveCommit(ctx, top, base)
	if err != nil {
		return nil, err
	}
	data, err := git.Show(ctx, top, rev, ModelPath)
	if err != nil && !errors.Is(err, git.ErrNotExist) {
		return nil, err
	}
	old, err := parseModel(data)
	if err != nil {
		return nil, fmt.Errorf("the base revision: %w", err)
	}
	return modelChanges(old, head), nil
}

// modelChanges returns the parts of the model that differ between old and
// head: layers, public, rules, vendored, component:<name> for an added or a
// removed component, and component:<name>.<field> for a changed field.
func modelChanges(old, head *Model) []string {
	var changes []string
	if !slices.EqualFunc(old.Layers, head.Layers, func(a, b Layer) bool {
		return a.Name == b.Name && a.Description == b.Description && sameSet(a.MayUse, b.MayUse)
	}) {
		changes = append(changes, "layers")
	}
	if !sameSet(old.Public, head.Public) {
		changes = append(changes, "public")
	}
	if !maps.Equal(old.Rules, head.Rules) {
		changes = append(changes, "rules")
	}
	if !sameSet(old.Vendored, head.Vendored) {
		changes = append(changes, "vendored")
	}
	for i := range head.Components {
		c := &head.Components[i]
		prior := old.component(c.Name)
		if prior == nil {
			changes = append(changes, componentChange+c.Name)
			continue
		}
		for _, field := range componentChanges(prior, c) {
			changes = append(changes, componentChange+c.Name+"."+field)
		}
	}
	for i := range old.Components {
		if head.component(old.Components[i].Name) == nil {
			changes = append(changes, componentChange+old.Components[i].Name)
		}
	}
	slices.Sort(changes)
	return changes
}

// componentChanges returns the fields that differ between two versions of a
// component.
func componentChanges(old, head *Component) []string {
	var fields []string
	if old.Layer != head.Layer {
		fields = append(fields, "layer")
	}
	if old.Responsibility != head.Responsibility {
		fields = append(fields, "responsibility")
	}
	lists := []struct {
		field     string
		old, head []string
	}{
		{"packages", old.Packages, head.Packages},
		{"uses", old.Uses, head.Uses},
		{"modules", old.Modules, head.Modules},
		{"test_uses", old.TestUses, head.TestUses},
		{"test_modules", old.TestModules, head.TestModules},
	}
	for _, l := range lists {
		if !sameSet(l.old, l.head) {
			fields = append(fields, l.field)
		}
	}
	return fields
}

// sameSet reports whether two lists hold the same entries in any order.
func sameSet(a, b []string) bool {
	a, b = slices.Clone(a), slices.Clone(b)
	slices.Sort(a)
	slices.Sort(b)
	return slices.Equal(slices.Compact(a), slices.Compact(b))
}

// checkRecord returns the findings of a design record against the head model.
// issue is the issue that the record must name, and changes are the actual
// model changes.
func checkRecord(m *Model, repo *repository, name string, r *Record, issue int, changes []string) []Finding {
	var findings []Finding
	add := func(rule, format string, args ...any) {
		findings = append(findings, m.finding(rule, name, fmt.Sprintf(format, args...)))
	}
	if problem := issueProblem(r.Issue, issue); problem != "" {
		add(RuleInvalidDesign, "%s", problem)
	}
	seen := map[string]bool{}
	for _, p := range r.Packages {
		if !validPath(p.Path) {
			add(RuleInvalidDesign, "the package path %s is not a clean relative path", quote(p.Path))
		}
		if seen[p.Path] {
			add(RuleInvalidDesign, "the package %s is listed twice", quote(p.Path))
		}
		seen[p.Path] = true
		findings = append(findings, checkRecordPackage(m, repo, name, p)...)
	}
	for _, change := range r.ModelChanges {
		if !changePattern.MatchString(change) {
			add(RuleInvalidDesign, "the model change %s is not layers, public, rules, vendored, or component:<name>[.<field>]", quote(change))
		}
	}
	for _, problem := range listProblems(r.ModelChanges, nil) {
		add(RuleInvalidDesign, "the model changes %s", problem)
	}
	if missing := setDifference(changes, r.ModelChanges); len(missing) > 0 {
		add(RuleDesignModelChangesDiffer, "the model changes %s are not in the record", quoteAll(missing))
	}
	if extra := setDifference(r.ModelChanges, changes); len(extra) > 0 {
		add(RuleDesignModelChangesDiffer, "the record lists the model changes %s, which did not change", quoteAll(extra))
	}
	return findings
}

// issueProblem returns the problem of the issue that a design record names,
// or "" when it is the positive issue number want.
func issueProblem(named, want int) string {
	if named <= 0 {
		return fmt.Sprintf("the design record names the issue %d, which is not a positive number", named)
	}
	if named != want {
		return fmt.Sprintf("the design record names issue %d, not issue %d", named, want)
	}
	return ""
}

// checkRecordPackage returns the findings of one package of a design record.
func checkRecordPackage(m *Model, repo *repository, name string, p RecordPackage) []Finding {
	var findings []Finding
	add := func(rule, format string, args ...any) {
		findings = append(findings, m.finding(rule, name, fmt.Sprintf(format, args...)))
	}
	if p.Removed {
		if len(p.Imports) > 0 || len(p.TestImports) > 0 {
			add(RuleInvalidDesign, "the removed package %s lists imports", quote(p.Path))
		}
		if owner := m.owner(p.Path); owner != nil {
			add(RuleDesignForbidden, "the removed package %s is still in the component %q", quote(p.Path), owner.Name)
		}
		return findings
	}
	c := m.component(p.Component)
	if c == nil {
		add(RuleDesignForbidden, "the package %s is in the unknown component %q", quote(p.Path), p.Component)
		return findings
	}
	if !slices.Contains(c.Packages, p.Path) {
		add(RuleDesignForbidden, "the package %s is not in the packages of %q", quote(p.Path), c.Name)
	}
	for _, problem := range listProblems(p.Imports, p.TestImports) {
		add(RuleInvalidDesign, "the imports of %s %s", quote(p.Path), problem)
	}
	for _, imp := range p.Imports {
		findings = append(findings, checkRecordImport(m, repo, name, c, p.Path, imp, false)...)
	}
	for _, imp := range p.TestImports {
		findings = append(findings, checkRecordImport(m, repo, name, c, p.Path, imp, true)...)
	}
	return findings
}

// checkRecordImport returns the findings of one import of a recorded package
// of component c.
func checkRecordImport(m *Model, repo *repository, name string, c *Component, pkg, imp string, test bool) []Finding {
	resolved := repo.resolve(repo.moduleOf(pkg), imp)
	switch resolved.kind {
	case importUnresolved, importModule:
		if module.CheckPath(imp) != nil {
			return []Finding{m.finding(RuleInvalidDesign, name, fmt.Sprintf("the import %s of %s is not a valid module path", quote(imp), quote(pkg)))}
		}
		if !mayImportModule(c, imp, test) {
			return []Finding{m.finding(RuleDesignForbidden, name, fmt.Sprintf("the package %s imports the module %s, which %q may not import", quote(pkg), quote(imp), c.Name))}
		}
	case importStandard:
		return []Finding{m.finding(RuleInvalidDesign, name, fmt.Sprintf("the package %s lists the standard library import %s; leave it out", quote(pkg), quote(imp)))}
	case importFirstParty:
		target := m.owner(resolved.dir)
		if target == nil {
			return []Finding{m.finding(RuleDesignForbidden, name, fmt.Sprintf("the package %s imports %s, which is in no component", quote(pkg), quote(imp)))}
		}
		if !mayUse(c, target.Name, test) {
			return []Finding{m.finding(RuleDesignForbidden, name, fmt.Sprintf("the package %s imports %s in %q, which %q does not use", quote(pkg), quote(imp), target.Name, c.Name))}
		}
	}
	return nil
}

// setDifference returns the entries of a that are not in b, sorted.
func setDifference(a, b []string) []string {
	var out []string
	for _, entry := range a {
		if !slices.Contains(b, entry) && !slices.Contains(out, entry) {
			out = append(out, entry)
		}
	}
	slices.Sort(out)
	return out
}

// quoteAll returns the quoted entries joined by commas, or the word none for
// an empty list.
func quoteAll(entries []string) string {
	if len(entries) == 0 {
		return "none"
	}
	return strings.Join(quoteEach(entries), ", ")
}
