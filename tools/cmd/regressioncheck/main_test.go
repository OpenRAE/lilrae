package main

import (
	"bytes"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

func TestRunRejectsInvalidArguments(t *testing.T) {
	t.Parallel()
	tests := []struct {
		args []string
		want int
	}{
		{args: []string{"-h"}, want: 0},
		{args: nil, want: 2},
		{args: []string{"-unknown"}, want: 2},
		{args: []string{"-base", "HEAD", "-issue", "-1"}, want: 2},
		{args: []string{"-base", "HEAD", "extra"}, want: 2},
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
	base := r.Commit(map[string]string{
		"go.mod":       "module example.com/fixture\n\ngo 1.27.0\n",
		"calc/calc.go": "// Package calc is a fixture.\npackage calc\n\n// Value returns a number.\nfunc Value() int { return 1 }\n",
	})
	r.Commit(map[string]string{
		"calc/calc.go": "// Package calc is a fixture.\npackage calc\n\n// Value returns a number.\nfunc Value() int { return 2 }\n",
		"calc/calc_test.go": "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestValue(t *testing.T) {\n" +
			"\tif Value() != 2 {\n\t\tt.Fatal(\"Value() != 2\")\n\t}\n}\n\n// regression: 7\nfunc TestMalformed(t *testing.T) {}\n",
	})
	tests := []struct {
		name string
		args []string
		code int
		want []string
	}{
		{
			name: "issue",
			args: []string{"-repo", r.Dir, "-base", base, "-issue", "7", "-bug"},
			code: 1,
			want: []string{
				"regressioncheck: base " + base + ", head ",
				"regressioncheck: issue #7, bug label true, 1 test(s) replayed\n  calc/calc_test.go: TestValue\n",
				"calc/calc_test.go:12: malformed regression comment",
				"regressioncheck: 1 finding(s)\n",
			},
		},
		{
			name: "no issue",
			args: []string{"-repo", r.Dir, "-base", base},
			code: 1,
			want: []string{"regressioncheck: the branch names no issue, so no test is replayed\n"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var stdout, stderr bytes.Buffer
			code := run(t.Context(), tc.args, &stdout, &stderr)
			if code != tc.code {
				t.Errorf("run(%q) = %d, want %d; stderr:\n%s", tc.args, code, tc.code, stderr.String())
			}
			for _, want := range tc.want {
				if !strings.Contains(stdout.String(), want) {
					t.Errorf("run(%q) output:\n%s\nwant it to contain %q", tc.args, stdout.String(), want)
				}
			}
		})
	}
}

func TestRunPassesACleanChange(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": "module example.com/fixture\n\ngo 1.27.0\n"})
	r.Commit(map[string]string{"README": "docs\n"})
	var stdout, stderr bytes.Buffer

	if code := run(t.Context(), []string{"-repo", r.Dir, "-base", base, "-issue", "7"}, &stdout, &stderr); code != 0 {
		t.Errorf("run() = %d, want 0; output:\n%s%s", code, stdout.String(), stderr.String())
	}
}

func TestRunReportsAnError(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	r.Commit(map[string]string{"go.mod": "module example.com/fixture\n\ngo 1.27.0\n"})
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-repo", r.Dir, "-base", "missing"}, &stdout, &stderr)

	if code != 2 || !strings.HasPrefix(stderr.String(), "regressioncheck: resolve \"missing\"") {
		t.Errorf("run(-base missing) = %d with stderr %q, want 2 and the resolve error", code, stderr.String())
	}
}
