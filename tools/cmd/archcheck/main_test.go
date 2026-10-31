package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

// model is a valid model of the fixture repository.
const model = `version: 1
layers:
  - name: core
    description: Holds the code.
    may_use: [core]
components:
  - name: calc
    layer: core
    responsibility: Adds numbers.
    packages: [internal/calc]
public: []
vendored: []
rules:
  unassigned-package: Fix unassigned-package.
  stale-package: Fix stale-package.
  forbidden-import: Fix forbidden-import.
  forbidden-module: Fix forbidden-module.
  unresolved-import: Fix unresolved-import.
  undeclared-public-package: Fix undeclared-public-package.
  invalid-model: Fix invalid-model.
  missing-design: Fix missing-design.
  invalid-design: Fix invalid-design.
  design-package-missing: Fix design-package-missing.
  design-imports-differ: Fix design-imports-differ.
  design-forbidden: Fix design-forbidden.
  design-model-changes-differ: Fix design-model-changes-differ.
  stale-diagram: Fix stale-diagram.
`

const (
	diagramBegin = "<!-- Generated from architecture/model.yaml by archcheck diagram. Do not edit. -->"
	diagramEnd   = "<!-- End of the generated diagram. -->"
)

// fixture returns a repository that passes the check, and its first commit.
func fixture(t *testing.T) (r *gittest.Repo, base string) {
	t.Helper()
	r = gittest.New(t)
	base = r.Commit(map[string]string{
		"architecture/model.yaml": model,
		"go.mod":                  "module example.com/app\n\ngo 1.27.0\n",
		"internal/calc/calc.go":   "// Package calc adds numbers.\npackage calc\n",
		"docs/architecture/issue-7-calc-design.md": "---\ndesign: 1\nissue: 7\n---\n\n# Design\n",
		"docs/arch.md": "# Architecture\n\n" + diagramBegin + "\nold\n" + diagramEnd + "\n",
	})
	return r, base
}

// failingWriter is an output that cannot be written.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("the output is closed") }

func TestRunRejectsInvalidArguments(t *testing.T) {
	t.Parallel()
	tests := []struct {
		args []string
		want int
	}{
		{args: nil, want: 2},
		{args: []string{"unknown"}, want: 2},
		{args: []string{"check", "-h"}, want: 0},
		{args: []string{"check", "-unknown"}, want: 2},
		{args: []string{"check", "extra"}, want: 2},
		{args: []string{"design", "-base", "HEAD"}, want: 2},
		{args: []string{"design", "note.md"}, want: 2},
		{args: []string{"design", "-base", "HEAD", "a.md", "b.md"}, want: 2},
		{args: []string{"pr", "-issue", "7"}, want: 2},
		{args: []string{"pr", "-base", "HEAD", "-issue", "-1"}, want: 2},
		{args: []string{"diagram", "extra"}, want: 2},
	}
	for _, tc := range tests {
		var stdout, stderr bytes.Buffer
		if got := run(t.Context(), tc.args, &stdout, &stderr); got != tc.want {
			t.Errorf("run(%q) = %d, want %d; stderr:\n%s", tc.args, got, tc.want, stderr.String())
		}
	}
}

func TestRunPrintsTheResult(t *testing.T) {
	t.Parallel()
	r, base := fixture(t)
	r.Commit(map[string]string{"internal/extra/extra.go": "package extra\n"})
	clean, _ := fixture(t)
	tests := []struct {
		name string
		args []string
		code int
		want string
	}{
		{name: "check passes", args: []string{"check", "-repo", clean.Dir}, want: "archcheck: check passed\n"},
		{
			name: "check finds a violation",
			args: []string{"check", "-repo", r.Dir},
			code: 1,
			want: "[unassigned-package] internal/extra: the package \"internal/extra\" is in no component\n    fix: Fix unassigned-package.\narchcheck: 1 finding(s)\n",
		},
		{name: "design passes", args: []string{"design", "-repo", clean.Dir, "-base", "HEAD", "docs/architecture/issue-7-calc-design.md"}, want: "archcheck: design passed\n"},
		{name: "pr without an issue", args: []string{"pr", "-repo", r.Dir, "-base", base}, code: 1, want: "[missing-design] the branch:"},
		{name: "pr with an issue", args: []string{"pr", "-repo", r.Dir, "-base", base, "-issue", "7"}, code: 1, want: "[design-package-missing] docs/architecture/issue-7-calc-design.md:"},
		{name: "pr of a promotion", args: []string{"pr", "-repo", clean.Dir, "-base", "HEAD", "-promotion"}, want: "archcheck: pr passed\n"},
		{name: "stale diagram", args: []string{"diagram", "-repo", clean.Dir, "-doc", "docs/arch.md"}, code: 1, want: "[stale-diagram] docs/arch.md:"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var stdout, stderr bytes.Buffer
			code := run(t.Context(), tc.args, &stdout, &stderr)
			if code != tc.code {
				t.Errorf("run(%q) = %d, want %d; stderr:\n%s", tc.args, code, tc.code, stderr.String())
			}
			if !strings.Contains(stdout.String(), tc.want) {
				t.Errorf("run(%q) output:\n%s\nwant it to contain %q", tc.args, stdout.String(), tc.want)
			}
		})
	}
}

func TestRunWritesTheDiagram(t *testing.T) {
	t.Parallel()
	r, _ := fixture(t)
	var stdout, stderr bytes.Buffer

	if code := run(t.Context(), []string{"diagram", "-repo", r.Dir, "-doc", "docs/arch.md", "-write"}, &stdout, &stderr); code != 0 {
		t.Fatalf("run(diagram -write) = %d, want 0; stderr:\n%s", code, stderr.String())
	}

	data, err := os.ReadFile(filepath.Join(r.Dir, "docs", "arch.md"))
	if err != nil {
		t.Fatal(err)
	}
	if want := "        component_calc[calc]\n"; !strings.Contains(string(data), want) {
		t.Errorf("the document after diagram -write is\n%s\nwant it to contain %q", data, want)
	}
}

func TestRunReportsAFailure(t *testing.T) {
	t.Parallel()
	r, _ := fixture(t)
	tests := []struct {
		name string
		args []string
		want string
	}{
		{name: "no repository", args: []string{"check", "-repo", t.TempDir()}, want: "archcheck: git rev-parse --show-toplevel: "},
		{name: "control characters in an error", args: []string{"design", "-repo", r.Dir, "-base", "HEAD", "docs/a\nb.md"}, want: `docs/a\nb.md`},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var stdout, stderr bytes.Buffer
			if code := run(t.Context(), tc.args, &stdout, &stderr); code != 2 {
				t.Errorf("run(%q) = %d, want 2", tc.args, code)
			}
			if got := stderr.String(); !strings.Contains(got, tc.want) || strings.Count(got, "\n") != 1 {
				t.Errorf("run(%q) stderr = %q, want one line that contains %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestRunReportsAClosedOutput(t *testing.T) {
	t.Parallel()
	clean, _ := fixture(t)
	r, _ := fixture(t)
	r.Commit(map[string]string{"internal/extra/extra.go": "package extra\n"})
	for _, args := range [][]string{{"check", "-repo", clean.Dir}, {"check", "-repo", r.Dir}} {
		var stderr bytes.Buffer
		if code := run(t.Context(), args, failingWriter{}, &stderr); code != 2 {
			t.Errorf("run(%q) with a closed output = %d, want 2", args, code)
		}
	}
}
