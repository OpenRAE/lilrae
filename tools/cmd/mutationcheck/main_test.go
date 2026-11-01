package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

const goMod = "module example.com/fixture\n\ngo 1.27.0\n"

// files returns the paths of a thresholds file and of a fake Gremlins program
// that writes report.
func files(t *testing.T, report string) (thresholds, gremlins string) {
	t.Helper()
	dir := t.TempDir()
	thresholds = filepath.Join(dir, "thresholds.json")
	if err := os.WriteFile(thresholds, []byte(`{"efficacy": 80, "mutant_coverage": 90}`), 0o600); err != nil {
		t.Fatal(err)
	}
	gremlins = filepath.Join(dir, "gremlins")
	script := "#!/bin/sh\nexit 0\n"
	if report != "" {
		script = "#!/bin/sh\ncat > \"$3\" <<'EOF'\n" + report + "\nEOF\n"
	}
	if err := os.WriteFile(gremlins, []byte(script), 0o700); err != nil { //nolint:gosec // G306: the fake program needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}
	return thresholds, gremlins
}

func report(statuses ...string) string {
	var mutants []string
	for _, s := range statuses {
		mutants = append(mutants, `{"type": "ARITHMETIC_BASE", "status": "`+s+`", "line": 3, "column": 9}`)
	}
	return `{"files": [{"file_name": "calc/calc.go", "mutations": [` + strings.Join(mutants, ", ") + `]}]}`
}

func TestRunRejectsInvalidArguments(t *testing.T) {
	t.Parallel()
	tests := []struct {
		args []string
		want int
	}{
		{args: []string{"-h"}, want: 0},
		{args: []string{"-unknown"}, want: 2},
		{args: []string{"-thresholds", "t.json"}, want: 2},
		{args: []string{"-gremlins", "gremlins"}, want: 2},
	}
	for _, tc := range tests {
		var stdout, stderr bytes.Buffer
		if got := run(t.Context(), tc.args, &stdout, &stderr); got != tc.want {
			t.Errorf("run(%q) = %d, want %d; stderr:\n%s", tc.args, got, tc.want, stderr.String())
		}
	}
}

func TestRunPrintsTheReport(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": "package calc\n"})
	r.Commit(map[string]string{"calc/calc.go": "package calc // changed\n", "calc/calc_test.go": "package calc\n"})
	tests := []struct {
		name   string
		report string
		base   string
		code   int
		want   []string
	}{
		{
			name:   "full run",
			report: report("KILLED", "KILLED", "KILLED", "KILLED", "TIMED OUT"),
			want: []string{
				"mutationcheck: full run of 1 module(s)\n",
				"mutationcheck: killed 4, lived 0, not covered 0, timed out 1, not viable 0\n",
				"mutationcheck: efficacy 100.00% (threshold 80%)\n",
				"mutationcheck: mutant coverage 100.00% (threshold 90%)\n",
			},
		},
		{
			name:   "change below the thresholds",
			report: report("KILLED", "LIVED"),
			base:   base,
			code:   1,
			want: []string{
				"mutationcheck: base " + base + ": 1 changed production file(s) in 1 module(s)\n  calc/calc.go\n",
				"efficacy: 50.00% is below the threshold of 80%\n",
				"calc/calc.go:3:9: LIVED ARITHMETIC_BASE\n",
				"mutationcheck: 2 finding(s)\n",
			},
		},
		{
			name: "changed lines without a mutant",
			base: base,
			want: []string{"mutationcheck: the changed lines hold no mutant\n"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			thresholds, gremlins := files(t, tc.report)
			args := []string{"-repo", r.Dir, "-gremlins", gremlins, "-thresholds", thresholds}
			if tc.base != "" {
				args = append(args, "-base", tc.base)
			}
			var stdout, stderr bytes.Buffer
			code := run(t.Context(), append(args, "."), &stdout, &stderr)
			if code != tc.code {
				t.Errorf("run(%q) = %d, want %d; stderr:\n%s", args, code, tc.code, stderr.String())
			}
			for _, want := range tc.want {
				if !strings.Contains(stdout.String(), want) {
					t.Errorf("run(%q) output:\n%s\nwant it to contain %q", args, stdout.String(), want)
				}
			}
		})
	}
}

func TestRunReportsAChangeWithoutProductionCode(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod})
	r.Commit(map[string]string{"calc/calc_test.go": "package calc\n"})
	thresholds, gremlins := files(t, "")
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-repo", r.Dir, "-gremlins", gremlins, "-thresholds", thresholds, "-base", base, "."}, &stdout, &stderr)

	if want := "no Go production file changed, so no relevant input changed"; code != 0 || !strings.Contains(stdout.String(), want) {
		t.Errorf("run() = %d with output %q, want 0 and %q", code, stdout.String(), want)
	}
}

func TestRunReportsAnError(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	r.Commit(map[string]string{"go.mod": goMod})
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-repo", r.Dir, "-gremlins", "gremlins", "-thresholds", filepath.Join(t.TempDir(), "missing.json")}, &stdout, &stderr)

	if code != 2 || !strings.HasPrefix(stderr.String(), "mutationcheck: read the mutation thresholds") {
		t.Errorf("run(missing thresholds) = %d with stderr %q, want 2 and the read error", code, stderr.String())
	}
}
