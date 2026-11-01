package regression

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/OpenRAE/lilrae/tools/internal/git"
	"github.com/OpenRAE/lilrae/tools/internal/golayout"
)

// cleanupTimeout bounds the removal of the base worktree after a cancellation.
const cleanupTimeout = time.Minute

// replay runs each test on the base revision, with the test files and test
// data of the head revision in its package, and then on the head revision.
func replay(ctx context.Context, root, base, head string, tests []Test) (findings []Finding, err error) {
	tmp, err := os.MkdirTemp("", "regressioncheck-")
	if err != nil {
		return nil, fmt.Errorf("create the replay directory: %w", err)
	}
	defer func() { err = errors.Join(err, removeDir(tmp)) }()
	tree := filepath.Join(tmp, "base")
	if _, err = git.Run(ctx, root, "worktree", "add", "--detach", "--quiet", tree, base); err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, removeWorktree(ctx, root, tree)) }()
	baseTree, err := os.OpenRoot(tree)
	if err != nil {
		return nil, fmt.Errorf("open the base worktree: %w", err)
	}
	defer func() { err = errors.Join(err, baseTree.Close()) }()
	headTree, err := os.OpenRoot(root)
	if err != nil {
		return nil, fmt.Errorf("open the working tree: %w", err)
	}
	defer func() { err = errors.Join(err, headTree.Close()) }()
	return replayTests(ctx, root, head, baseTree, headTree, tests)
}

// replayTests runs each test in the base worktree and in the working tree.
func replayTests(ctx context.Context, root, head string, baseTree, headTree *os.Root, tests []Test) ([]Finding, error) {
	var findings []Finding
	prepared := map[string]bool{}
	for _, t := range tests {
		dir := path.Dir(t.File)
		if !prepared[dir] {
			if err := overlay(ctx, root, head, baseTree, dir); err != nil {
				return nil, err
			}
			prepared[dir] = true
		}
		found, err := runOn(ctx, baseTree, t, "base", failed)
		if err != nil {
			return nil, err
		}
		findings = append(findings, found...)
		found, err = runOn(ctx, headTree, t, "head", passed)
		if err != nil {
			return nil, err
		}
		findings = append(findings, found...)
	}
	return findings, nil
}

func removeDir(dir string) error {
	if err := os.RemoveAll(dir); err != nil {
		return fmt.Errorf("remove the replay directory: %w", err)
	}
	return nil
}

func removeWorktree(ctx context.Context, root, tree string) error {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), cleanupTimeout)
	defer cancel()
	_, err := git.Run(ctx, root, "worktree", "remove", "--force", tree)
	return err
}

// overlay makes the test files and the test data of dir in tree equal to
// those of the head revision.
func overlay(ctx context.Context, root, head string, tree *os.Root, dir string) error {
	if err := removeTestFiles(tree, dir); err != nil {
		return err
	}
	files, err := git.Files(ctx, root, head, dir)
	if err != nil {
		return err
	}
	for _, file := range files {
		rel := relative(dir, file.Path)
		isTestFile := !strings.Contains(rel, "/") && strings.HasSuffix(rel, "_test.go")
		// A testdata entry without a slash is a symlink to the test data.
		if !isTestFile && rel != "testdata" && !strings.HasPrefix(rel, "testdata/") {
			continue
		}
		if err := writeEntry(ctx, root, head, tree, file); err != nil {
			return err
		}
	}
	return nil
}

// removeTestFiles removes the test files and the test data of dir from tree.
func removeTestFiles(tree *os.Root, dir string) error {
	native := filepath.FromSlash(dir)
	entries, err := fs.ReadDir(tree.FS(), dir)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("read %s in the base worktree: %w", dir, err)
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		if err := tree.Remove(filepath.Join(native, entry.Name())); err != nil {
			return fmt.Errorf("remove a base test file: %w", err)
		}
	}
	if err := tree.RemoveAll(filepath.Join(native, "testdata")); err != nil {
		return fmt.Errorf("remove the base test data: %w", err)
	}
	return nil
}

// writeEntry writes a file of the head revision into tree.
func writeEntry(ctx context.Context, root, head string, tree *os.Root, entry git.Entry) error {
	data, err := git.Show(ctx, root, head, entry.Path)
	if err != nil {
		return err
	}
	name := filepath.FromSlash(entry.Path)
	if err = tree.MkdirAll(filepath.Dir(name), 0o750); err != nil {
		return fmt.Errorf("create the directory of %s: %w", entry.Path, err)
	}
	switch entry.Mode {
	case "120000":
		err = tree.Symlink(string(data), name)
	case "100755":
		err = tree.WriteFile(name, data, 0o700)
	default:
		err = tree.WriteFile(name, data, 0o600)
	}
	if err != nil {
		return fmt.Errorf("write %s into the base worktree: %w", entry.Path, err)
	}
	return nil
}

// runOn runs test t in tree and returns a finding unless the test has the
// wanted outcome. revision names the tree in the findings.
func runOn(ctx context.Context, tree *os.Root, t Test, revision string, want outcome) ([]Finding, error) {
	dir := path.Dir(t.File)
	module, ok, err := golayout.ModuleDir(tree.FS(), dir)
	if err != nil {
		return nil, err
	}
	if !ok {
		return []Finding{{Location: t.File, Message: fmt.Sprintf("%s: the package has no Go module on the %s revision", t.Name, revision)}}, nil
	}
	run, err := goTest(ctx, filepath.Join(tree.Name(), filepath.FromSlash(module)), pattern(module, dir), t.Name)
	if err != nil {
		return nil, err
	}
	return judge(t, revision, want, run), nil
}

// judge returns a finding unless the run has the wanted outcome.
func judge(t Test, revision string, want outcome, run testRun) []Finding {
	if run.buildFailed {
		message := fmt.Sprintf("%s: the test does not build on the %s revision", t.Name, revision)
		if want == failed {
			message += "; a regression test must use the API of the base revision"
		}
		if len(run.buildOutput) > 0 {
			message += ": " + strings.Join(run.buildOutput, "; ")
		}
		return []Finding{{Location: t.File, Message: message}}
	}
	if run.outcome != want {
		return []Finding{{Location: t.File, Message: fmt.Sprintf("%s: the test %s on the %s revision; it must %s there",
			t.Name, run.outcome, revision, verb(want))}}
	}
	return nil
}

func verb(want outcome) string {
	if want == passed {
		return "pass"
	}
	return "fail"
}

// pattern returns the package pattern of dir for the go command in module.
func pattern(module, dir string) string {
	rel := relative(module, dir)
	if rel == "" {
		return "."
	}
	return "./" + rel
}

// relative returns p relative to dir. Both are slash-separated repository
// paths, and dir is p or a parent of p.
func relative(dir, p string) string {
	if dir == "." {
		return p
	}
	if p == dir {
		return ""
	}
	return strings.TrimPrefix(p, dir+"/")
}

// goTest runs one test of a package with "go test -json" and returns its
// result. A go command that fails before it runs the package counts as a
// build failure.
func goTest(ctx context.Context, moduleDir, pkg, name string) (testRun, error) {
	// G204 is a false positive: the program is fixed, no shell runs, name is
	// an identifier from the Go parser, and pkg is a "./" path in the module.
	cmd := exec.CommandContext(ctx, "go", "test", "-json", "-count=1", "-run", "^"+name+"$", pkg) //nolint:gosec // G204: fixed program, argv without a shell.
	cmd.Dir = moduleDir
	cmd.Env = append(os.Environ(), "GOWORK=off")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	runErr := cmd.Run()
	if err := ctx.Err(); err != nil {
		return testRun{}, fmt.Errorf("run go test: %w", err)
	}
	var exitErr *exec.ExitError
	if runErr != nil && !errors.As(runErr, &exitErr) {
		return testRun{}, fmt.Errorf("run go test in %s: %w", moduleDir, runErr)
	}
	run, err := parseRun(&stdout, name)
	if err != nil {
		return testRun{}, err
	}
	if runErr != nil && run.outcome == notRun && !run.buildFailed {
		run.buildFailed = true
		for line := range strings.Lines(stderr.String()) {
			if len(run.buildOutput) == maxBuildLines {
				break
			}
			if line = strings.TrimSpace(line); line != "" {
				run.buildOutput = append(run.buildOutput, line)
			}
		}
	}
	return run, nil
}
