package regression

import (
	"bytes"
	"context"
	"fmt"
	"path"
	"strings"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

// Config describes one regression check.
type Config struct {
	// Repo is a directory in the working tree of the head revision.
	Repo string
	// Base is the base revision of the change.
	Base string
	// Issue is the issue of the change, or 0 when the branch names no issue.
	Issue int
	// Bug reports that the issue has the bug label.
	Bug bool
}

// Test identifies a test function.
type Test struct {
	// File is the test file, relative to the repository root.
	File string
	// Name is the name of the test function.
	Name string
}

// Finding is a violation of the regression test rules.
type Finding struct {
	// Location is a file and, when one applies, a line.
	Location string
	// Message describes the violation.
	Message string
}

func (f Finding) String() string {
	return f.Location + ": " + f.Message
}

// Report is the result of a regression check.
type Report struct {
	// Base and Head are the full names of the compared commits.
	Base, Head string
	// Selected lists the tests that the check replayed.
	Selected []Test
	// Findings lists the violations. The check passed when it is empty.
	Findings []Finding
}

// Check runs the regression check on the change from [Config.Base] to HEAD. The
// working tree must hold the head revision. Check returns an error when it
// cannot complete, and a report with findings when the change breaks a rule.
func Check(ctx context.Context, cfg Config) (Report, error) {
	root, err := git.TopLevel(ctx, cfg.Repo)
	if err != nil {
		return Report{}, err
	}
	base, err := git.ResolveCommit(ctx, root, cfg.Base)
	if err != nil {
		return Report{}, err
	}
	head, err := git.ResolveCommit(ctx, root, "HEAD")
	if err != nil {
		return Report{}, err
	}
	scan, err := scanChanges(ctx, root, base, head, cfg.Issue)
	if err != nil {
		return Report{}, err
	}
	report := Report{Base: base, Head: head, Findings: scan.findings}
	if cfg.Issue == 0 {
		return report, nil
	}
	if report.Selected, err = selectChanged(ctx, root, base, scan.candidates); err != nil {
		return Report{}, err
	}
	if cfg.Bug && scan.productionChanged && len(report.Selected) == 0 {
		report.Findings = append(report.Findings, Finding{
			Location: fmt.Sprintf("issue #%d", cfg.Issue),
			Message: fmt.Sprintf("the issue has the bug label and the change edits Go production code, "+
				"but the change adds or changes no test with \"regression: #%d\"", cfg.Issue),
		})
	}
	if len(report.Selected) == 0 {
		return report, nil
	}
	findings, err := replay(ctx, root, base, head, report.Selected)
	if err != nil {
		return Report{}, err
	}
	report.Findings = append(report.Findings, findings...)
	return report, nil
}

// changes is what the check reads from the changed Go files.
type changes struct {
	// candidates are the tests for the issue in the changed test files.
	candidates []candidate
	// findings are the problems of the regression comments.
	findings []Finding
	// productionChanged reports a changed Go file that is not a test file.
	productionChanged bool
}

// scanChanges reads the Go files that differ between base and head.
func scanChanges(ctx context.Context, root, base, head string, issue int) (changes, error) {
	files, err := git.ChangedFiles(ctx, root, base, head, "*.go")
	if err != nil {
		return changes{}, err
	}
	var scan changes
	for _, file := range files {
		if golayout.Ignored(file.Path) {
			continue
		}
		if !strings.HasSuffix(file.Path, "_test.go") {
			// A deleted production file is a change of production code too.
			scan.productionChanged = true
			continue
		}
		if file.Deleted {
			continue
		}
		found, findings, err := readChangedTestFile(ctx, root, head, file.Path, issue)
		if err != nil {
			return changes{}, err
		}
		scan.candidates = append(scan.candidates, found...)
		scan.findings = append(scan.findings, findings...)
	}
	return scan, nil
}

// candidate is a test of the head revision that carries the issue of the
// change.
type candidate struct {
	file string
	fn   testFunc
}

// readChangedTestFile returns the tests for issue in a changed test file and
// the findings of its regression comments.
func readChangedTestFile(ctx context.Context, root, head, file string, issue int) ([]candidate, []Finding, error) {
	src, err := git.Show(ctx, root, head, file)
	if err != nil {
		return nil, nil, err
	}
	funcs, problems, err := parseTestFile(file, src)
	if err != nil {
		return nil, nil, err
	}
	var findings []Finding
	for _, p := range problems {
		findings = append(findings, Finding{
			Location: fmt.Sprintf("%s:%d", file, p.line),
			Message:  p.message,
		})
	}
	var found []candidate
	for _, fn := range funcs {
		if issue != 0 && fn.issue == issue {
			found = append(found, candidate{file: file, fn: fn})
		}
	}
	return found, findings, nil
}

// selectChanged returns the candidates that the base revision does not have
// with the same package, name, issue, and declaration. The order follows the
// candidates, which follow the sorted file list of git diff.
func selectChanged(ctx context.Context, root, base string, candidates []candidate) ([]Test, error) {
	baseFuncs := map[string]map[string]testFunc{}
	var selected []Test
	for _, c := range candidates {
		dir := path.Dir(c.file)
		funcs, ok := baseFuncs[dir]
		if !ok {
			var err error
			if funcs, err = packageTests(ctx, root, base, dir); err != nil {
				return nil, err
			}
			baseFuncs[dir] = funcs
		}
		old, ok := funcs[c.fn.name]
		if ok && old.issue == c.fn.issue && bytes.Equal(old.source, c.fn.source) {
			continue
		}
		selected = append(selected, Test{File: c.file, Name: c.fn.name})
	}
	return selected, nil
}

// packageTests returns the test functions of the test files of dir at rev,
// by name. It skips the test files that the go command ignores.
func packageTests(ctx context.Context, root, rev, dir string) (map[string]testFunc, error) {
	entries, err := git.Files(ctx, root, rev, dir)
	if err != nil {
		return nil, err
	}
	funcs := map[string]testFunc{}
	for _, entry := range entries {
		if path.Dir(entry.Path) != dir || !strings.HasSuffix(entry.Path, "_test.go") || golayout.Ignored(entry.Path) {
			continue
		}
		src, err := git.Show(ctx, root, rev, entry.Path)
		if err != nil {
			return nil, err
		}
		parsed, _, err := parseTestFile(entry.Path, src)
		if err != nil {
			return nil, err
		}
		for _, fn := range parsed {
			funcs[fn.name] = fn
		}
	}
	return funcs, nil
}
