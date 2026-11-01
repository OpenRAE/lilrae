package mutation

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

// Config describes one run of the gate.
type Config struct {
	// Repo is a directory in the working tree of the head revision.
	Repo string
	// Base is the base revision of the change. An empty Base means a full
	// run of each module.
	Base string
	// Modules are the directories of the Go modules that have packages,
	// relative to the repository root.
	Modules []string
	// Gremlins is the path of the gremlins program.
	Gremlins string
	// Thresholds is the path of the thresholds file.
	Thresholds string
	// Workers is the number of mutants that Gremlins tests at the same time.
	// Zero means the Gremlins default, one for each CPU.
	Workers int
	// TimeoutCoefficient multiplies the time of the first test run to give
	// the timeout of each mutant. Zero means the Gremlins default of 3.
	TimeoutCoefficient int
	// Log receives the output of Gremlins.
	Log io.Writer
}

// Finding is a violation of the gate.
type Finding struct {
	// Location is a file and position, or the name of the measure.
	Location string
	// Message describes the violation.
	Message string
}

func (f Finding) String() string {
	return f.Location + ": " + f.Message
}

// Report is the result of a run of the gate.
type Report struct {
	// Base is the full name of the base commit, or empty for a full run.
	Base string
	// Changed lists the changed production files. It is empty for a full run.
	Changed []string
	// Mutated lists the modules where Gremlins ran.
	Mutated []string
	// Counts are the numbers of mutants by status.
	Counts Counts
	// Thresholds are the thresholds that the run applied.
	Thresholds Thresholds
	// Findings lists the violations. The gate passed when it is empty.
	Findings []Finding
}

// Check runs the gate. It returns an error when the gate cannot complete.
func Check(ctx context.Context, cfg Config) (Report, error) {
	root, err := git.TopLevel(ctx, cfg.Repo)
	if err != nil {
		return Report{}, err
	}
	data, err := os.ReadFile(cfg.Thresholds)
	if err != nil {
		return Report{}, fmt.Errorf("read the mutation thresholds: %w", err)
	}
	report := Report{Mutated: cfg.Modules}
	if report.Thresholds, err = ParseThresholds(data); err != nil {
		return Report{}, err
	}
	if cfg.Base != "" {
		var c change
		if c, err = readChange(ctx, root, cfg, report.Thresholds); err != nil {
			return Report{}, err
		}
		report.Base, report.Changed, report.Mutated, report.Findings = c.base, c.files, c.modules, c.findings
	}
	var open []Mutant
	for _, module := range report.Mutated {
		counts, found, err := mutate(ctx, cfg, root, module, report.Base)
		if err != nil {
			return Report{}, err
		}
		report.Counts = report.Counts.add(counts)
		open = append(open, found...)
	}
	report.Findings = append(report.Findings, evaluate(report.Counts, report.Thresholds, open)...)
	return report, nil
}

// change is what the gate reads from a change.
type change struct {
	// base is the full name of the base commit.
	base string
	// files are the changed production files of the modules.
	files []string
	// modules are the modules that have changed production files.
	modules []string
	// findings are the thresholds that the change lowers.
	findings []Finding
}

// readChange reads the change from [Config.Base] to HEAD.
func readChange(ctx context.Context, root string, cfg Config, thresholds Thresholds) (c change, err error) {
	base, err := git.ResolveCommit(ctx, root, cfg.Base)
	if err != nil {
		return change{}, err
	}
	head, err := git.ResolveCommit(ctx, root, "HEAD")
	if err != nil {
		return change{}, err
	}
	c.base = base
	if c.findings, err = loweredThresholds(ctx, root, base, cfg.Thresholds, thresholds); err != nil {
		return change{}, err
	}
	files, err := git.ChangedFiles(ctx, root, base, head, "*.go")
	if err != nil {
		return change{}, err
	}
	tree, err := os.OpenRoot(root)
	if err != nil {
		return change{}, fmt.Errorf("open the working tree: %w", err)
	}
	defer func() { err = errors.Join(err, tree.Close()) }()
	if c.files, c.modules, err = productionChanges(tree.FS(), files, cfg.Modules); err != nil {
		return change{}, err
	}
	return c, nil
}

// productionChanges returns the changed production files of files that are
// in one of modules, and the modules that hold them. A deleted file has no
// line to mutate.
func productionChanges(tree fs.FS, files []git.Change, modules []string) (changed, mutated []string, err error) {
	for _, file := range files {
		if file.Deleted || strings.HasSuffix(file.Path, "_test.go") || golayout.Ignored(file.Path) {
			continue
		}
		module, ok, err := golayout.ModuleDir(tree, path.Dir(file.Path))
		if err != nil {
			return nil, nil, err
		}
		if !ok || !slices.Contains(modules, module) {
			continue
		}
		changed = append(changed, file.Path)
		if !slices.Contains(mutated, module) {
			mutated = append(mutated, module)
		}
	}
	return changed, mutated, nil
}

// loweredThresholds returns a finding when the thresholds file is in the
// repository and the change lowers a threshold of the base revision.
func loweredThresholds(ctx context.Context, root, base, file string, current Thresholds) ([]Finding, error) {
	abs, err := filepath.Abs(file)
	if err != nil {
		return nil, fmt.Errorf("locate the mutation thresholds: %w", err)
	}
	rel, err := filepath.Rel(root, abs)
	if err != nil {
		return nil, fmt.Errorf("locate the mutation thresholds: %w", err)
	}
	if !filepath.IsLocal(rel) {
		// A thresholds file outside the repository has no base version.
		return nil, nil
	}
	name := filepath.ToSlash(rel)
	data, err := git.Show(ctx, root, base, name)
	if errors.Is(err, git.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	old, err := ParseThresholds(data)
	if err != nil {
		return nil, fmt.Errorf("the base revision of %s: %w", name, err)
	}
	if lowered := current.lowered(old); len(lowered) > 0 {
		return []Finding{{Location: name, Message: "the change lowers a threshold: " + strings.Join(lowered, ", ")}}, nil
	}
	return nil, nil
}

// mutate runs Gremlins in module and returns its counts and the mutants that
// lived or are not covered.
func mutate(ctx context.Context, cfg Config, root, module, base string) (counts Counts, open []Mutant, err error) {
	dir, err := os.MkdirTemp("", "mutationcheck-")
	if err != nil {
		return Counts{}, nil, fmt.Errorf("create the Gremlins report directory: %w", err)
	}
	defer func() {
		if rmErr := os.RemoveAll(dir); rmErr != nil {
			err = errors.Join(err, fmt.Errorf("remove the Gremlins report directory: %w", rmErr))
		}
	}()
	reports, err := os.OpenRoot(dir)
	if err != nil {
		return Counts{}, nil, fmt.Errorf("open the Gremlins report directory: %w", err)
	}
	defer func() { err = errors.Join(err, reports.Close()) }()
	// An empty file shows afterwards that Gremlins wrote no report.
	const reportName = "report.json"
	if err = reports.WriteFile(reportName, nil, 0o600); err != nil {
		return Counts{}, nil, fmt.Errorf("create the Gremlins report file: %w", err)
	}
	// Gremlins reads 0 workers as one for each CPU and a coefficient of 0
	// as its default.
	args := []string{"unleash", "--output", filepath.Join(dir, reportName),
		"--workers", strconv.Itoa(cfg.Workers), "--timeout-coefficient", strconv.Itoa(cfg.TimeoutCoefficient)}
	if base != "" {
		args = append(args, "--diff", base)
	}
	// G204 is a false positive: the program comes from the configuration, no
	// shell runs, and the arguments are fixed or a full commit name.
	cmd := exec.CommandContext(ctx, cfg.Gremlins, append(args, ".")...) //nolint:gosec // G204: fixed program, argv without a shell.
	cmd.Dir = filepath.Join(root, filepath.FromSlash(module))
	cmd.Env = gremlinsEnv(os.Environ())
	cmd.Stdout = cfg.Log
	cmd.Stderr = cfg.Log
	if err = cmd.Run(); err != nil {
		return Counts{}, nil, fmt.Errorf("run Gremlins in %s: %w", module, err)
	}
	data, err := reports.ReadFile(reportName)
	if err != nil {
		return Counts{}, nil, fmt.Errorf("read the Gremlins report of %s: %w", module, err)
	}
	if len(data) == 0 {
		// Gremlins writes no report when the module has no mutant.
		return Counts{}, nil, nil
	}
	return readReport(data, module)
}

// gremlinsEnv returns the environment of Gremlins. Each setting works around
// a defect of Gremlins v0.6.0 that the design note of #1553 lists with its
// issue in OpenRAE/go-rae-gremlins:
//
//   - Git reads no global or system configuration of the host, because a
//     setting such as diff.noprefix changes the diff that Gremlins parses.
//   - Git writes diff paths relative to the module, because Gremlins compares
//     them with module paths (#36).
//   - Git writes no context lines, because Gremlins reads one range of
//     changed lines from each hunk, and a hunk with context can hold two
//     edits (#40).
//   - Go does not reuse cached test results, because Gremlins derives the
//     mutant timeout from the time of the first test run (#22).
func gremlinsEnv(env []string) []string {
	count := 0
	goflags := ""
	for _, kv := range env {
		key, value, _ := strings.Cut(kv, "=")
		switch key {
		case "GIT_CONFIG_COUNT":
			if n, err := strconv.Atoi(value); err == nil {
				count = max(n, 0)
			}
		case "GOFLAGS":
			goflags = value
		}
	}
	out := slices.Concat(env, []string{
		"GOWORK=off",
		"GOFLAGS=" + strings.TrimSpace(goflags+" -count=1"),
		"GIT_CONFIG_GLOBAL=" + os.DevNull,
		"GIT_CONFIG_NOSYSTEM=1",
	})
	settings := []struct{ key, value string }{{"diff.relative", "true"}, {"diff.context", "0"}}
	for i, s := range settings {
		out = append(out, fmt.Sprintf("GIT_CONFIG_KEY_%d=%s", count+i, s.key), fmt.Sprintf("GIT_CONFIG_VALUE_%d=%s", count+i, s.value))
	}
	return append(out, fmt.Sprintf("GIT_CONFIG_COUNT=%d", count+len(settings)))
}

// evaluate applies the thresholds to the counts.
func evaluate(counts Counts, thresholds Thresholds, open []Mutant) []Finding {
	if counts.Killed+counts.Lived+counts.NotCovered+counts.TimedOut == 0 {
		return nil
	}
	if counts.Killed+counts.Lived+counts.NotCovered == 0 {
		return []Finding{{Location: "mutants", Message: fmt.Sprintf("each of the %d mutants timed out, so the tests measure nothing", counts.TimedOut)}}
	}
	var findings []Finding
	if efficacy, ok := counts.Efficacy(); ok && efficacy < thresholds.Efficacy {
		findings = append(findings, Finding{Location: "efficacy", Message: fmt.Sprintf("%.2f%% is below the threshold of %g%%", efficacy, thresholds.Efficacy)})
	}
	if coverage, ok := counts.MutantCoverage(); ok && coverage < thresholds.MutantCoverage {
		findings = append(findings, Finding{Location: "mutant coverage", Message: fmt.Sprintf("%.2f%% is below the threshold of %g%%", coverage, thresholds.MutantCoverage)})
	}
	if len(findings) == 0 {
		return nil
	}
	for _, m := range open {
		findings = append(findings, Finding{Location: fmt.Sprintf("%s:%d:%d", m.File, m.Line, m.Column), Message: m.Status + " " + m.Type})
	}
	return findings
}
