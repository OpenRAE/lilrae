package mutation_test

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/lilrae/tools/internal/gittest"
	"github.com/OpenRAE/lilrae/tools/internal/mutation"
)

const goMod = "module example.com/fixture\n\ngo 1.27.0\n"

// adultSource returns a package calc whose Adult compares an age with 18.
func adultSource(doc string) string {
	return "// Package calc is a fixture.\npackage calc\n\n" + doc + "func Adult(age int) bool {\n\treturn age >= 18\n}\n"
}

// weakTest misses the boundary, so the boundary mutant lives.
const weakTest = "package calc\n\nimport \"testing\"\n\nfunc TestAdult(t *testing.T) {\n" +
	"\tif !Adult(30) {\n\t\tt.Error(\"Adult(30) = false, want true\")\n\t}\n}\n"

// strongTest checks the boundary, so each mutant dies.
const strongTest = "package calc\n\nimport \"testing\"\n\nfunc TestAdult(t *testing.T) {\n" +
	"\tfor age, want := range map[int]bool{17: false, 18: true, 30: true} {\n" +
	"\t\tif got := Adult(age); got != want {\n\t\t\tt.Errorf(\"Adult(%d) = %t, want %t\", age, got, want)\n\t\t}\n\t}\n}\n"

const thresholds = `{"efficacy": 80, "mutant_coverage": 90}`

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}

// gremlins returns the path of the pinned Gremlins program.
func gremlins(t *testing.T) string {
	t.Helper()
	out, err := exec.CommandContext(t.Context(), "go", "tool", "-n", "gremlins").Output()
	if err != nil {
		t.Fatalf("go tool -n gremlins: %v", err)
	}
	return strings.TrimSpace(string(out))
}

// fakeGremlins returns a program that writes report as the Gremlins report.
// An empty report means that the program writes nothing, as Gremlins does for
// a module without mutants.
func fakeGremlins(t *testing.T, report string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "gremlins")
	script := "#!/bin/sh\nexit 0\n"
	if report != "" {
		script = "#!/bin/sh\n# Arguments: unleash --output FILE ...\ncat > \"$3\" <<'EOF'\n" + report + "\nEOF\n"
	}
	writeFile(t, path, script)
	if err := os.Chmod(path, 0o700); err != nil { //nolint:gosec // G302: the fake program needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}
	return path
}

// thresholdsFile returns a file with thresholds, outside the repository.
func thresholdsFile(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "thresholds.json")
	writeFile(t, path, thresholds)
	return path
}

func check(t *testing.T, cfg mutation.Config) mutation.Report {
	t.Helper()
	var log bytes.Buffer
	cfg.Log = &log
	report, err := mutation.Check(t.Context(), cfg)
	if err != nil {
		t.Fatalf("Check(base %q, modules %q) returned error %v\nGremlins output:\n%s", cfg.Base, cfg.Modules, err, log.String())
	}
	return report
}

func messages(report mutation.Report) []string {
	var out []string
	for _, f := range report.Findings {
		out = append(out, f.String())
	}
	return out
}

func TestCheckFailsOnLivedMutantsInTheChangedLinesOfANestedModule(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"README": "fixture\n", "sub/go.mod": goMod})
	r.Commit(map[string]string{"sub/calc/calc.go": adultSource("// Adult reports whether age is 18 or more.\n"), "sub/calc/calc_test.go": weakTest})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"sub"}, Gremlins: gremlins(t), Thresholds: thresholdsFile(t)})

	if report.Counts.Lived == 0 {
		t.Fatalf("Counts = %+v, want lived mutants: Gremlins must see the changed lines of a nested module", report.Counts)
	}
	got := messages(report)
	if len(got) < 2 || !strings.HasPrefix(got[0], "efficacy: ") || !strings.Contains(got[1], "sub/calc/calc.go:") || !strings.Contains(got[1], "LIVED") {
		t.Errorf("findings = %q, want the efficacy finding and then each lived mutant with its repository path", got)
	}
}

func TestCheckPassesWhenTheTestsKillEachMutant(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod})
	r.Commit(map[string]string{"calc/calc.go": adultSource("// Adult reports whether age is 18 or more.\n"), "calc/calc_test.go": strongTest})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"."}, Gremlins: gremlins(t), Thresholds: thresholdsFile(t)})

	if got := messages(report); len(got) != 0 || report.Counts.Killed == 0 {
		t.Errorf("findings = %q, counts = %+v; want no finding and killed mutants", got, report.Counts)
	}
}

func TestCheckPassesChangedLinesWithoutAMutant(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": adultSource("// Adult reports whether age is adult.\n"), "calc/calc_test.go": weakTest})
	r.Commit(map[string]string{"calc/calc.go": adultSource("// Adult reports whether age is 18 or more.\n")})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"."}, Gremlins: gremlins(t), Thresholds: thresholdsFile(t)})

	if diff := cmp.Diff([]string{"calc/calc.go"}, report.Changed); diff != "" {
		t.Errorf("Changed mismatch (-want +got):\n%s", diff)
	}
	if got := messages(report); len(got) != 0 || report.Counts != (mutation.Counts{}) {
		t.Errorf("findings = %q, counts = %+v; want no finding and no mutant for a comment change", got, report.Counts)
	}
}

func TestCheckDoesNotRunWithoutAProductionChange(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": adultSource("// Adult reports whether age is adult.\n")})
	r.Commit(map[string]string{"calc/calc_test.go": weakTest, "calc/testdata/case.go": "package calc\n", "other/main.go": "package main\n"})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"calc-module"}, Gremlins: "/nonexistent/gremlins", Thresholds: thresholdsFile(t)})

	if len(report.Changed) != 0 || len(report.Mutated) != 0 || len(report.Findings) != 0 {
		t.Errorf("Check() = %+v, want no changed file, no mutated module, and no finding", report)
	}
}

func TestCheckRejectsALoweredThreshold(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "thresholds.json": `{"efficacy": 85, "mutant_coverage": 90}`})
	r.Commit(map[string]string{"thresholds.json": `{"efficacy": 80, "mutant_coverage": 95}`})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Gremlins: "/nonexistent/gremlins", Thresholds: filepath.Join(r.Dir, "thresholds.json")})

	want := []string{"thresholds.json: the change lowers a threshold: efficacy 80 < 85"}
	if diff := cmp.Diff(want, messages(report)); diff != "" {
		t.Errorf("findings mismatch (-want +got):\n%s", diff)
	}
}

func TestCheckEvaluatesTheGremlinsReport(t *testing.T) {
	t.Parallel()
	mutant := func(status string) string {
		return `{"type": "CONDITIONALS_BOUNDARY", "status": "` + status + `", "line": 6, "column": 7}`
	}
	report := func(statuses ...string) string {
		var mutants []string
		for _, s := range statuses {
			mutants = append(mutants, mutant(s))
		}
		return `{"go_module": "example.com/fixture", "files": [{"file_name": "calc/calc.go", "mutations": [` + strings.Join(mutants, ", ") + `]}]}`
	}
	tests := []struct {
		name   string
		report string
		want   []string
	}{
		{name: "no report", report: ""},
		{name: "skipped and not viable only", report: report("SKIPPED", "NOT VIABLE")},
		{name: "above the thresholds", report: report("KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "LIVED", "TIMED OUT")},
		{name: "at the efficacy threshold", report: report("KILLED", "KILLED", "KILLED", "KILLED", "LIVED")},
		{name: "at the coverage threshold", report: report("KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "KILLED", "NOT COVERED")},
		{
			name:   "below the efficacy threshold",
			report: report("KILLED", "LIVED"),
			want:   []string{"efficacy: 50.00% is below the threshold of 80%", "calc/calc.go:6:7: LIVED CONDITIONALS_BOUNDARY"},
		},
		{
			name:   "below the coverage threshold",
			report: report("KILLED", "NOT COVERED"),
			want:   []string{"mutant coverage: 50.00% is below the threshold of 90%", "calc/calc.go:6:7: NOT COVERED CONDITIONALS_BOUNDARY"},
		},
		{
			name:   "lived and timed out",
			report: report("LIVED", "TIMED OUT"),
			want:   []string{"efficacy: 0.00% is below the threshold of 80%", "calc/calc.go:6:7: LIVED CONDITIONALS_BOUNDARY"},
		},
		{
			name:   "each mutant timed out",
			report: report("TIMED OUT", "TIMED OUT"),
			want:   []string{"mutants: each of the 2 mutants timed out, so the tests measure nothing"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := gittest.New(t)
			r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": adultSource("// Adult reports whether age is adult.\n")})

			got := check(t, mutation.Config{Repo: r.Dir, Modules: []string{"."}, Gremlins: fakeGremlins(t, tc.report), Thresholds: thresholdsFile(t)})

			if diff := cmp.Diff(tc.want, messages(got)); diff != "" {
				t.Errorf("findings mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestCheckRejectsAnInvalidGremlinsReport(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		report string
		want   string
	}{
		{name: "not JSON", report: "{", want: "decode the Gremlins report of ."},
		{name: "unknown status", report: `{"files": [{"file_name": "a.go", "mutations": [{"type": "X", "status": "NEW", "line": 1}]}]}`, want: `unknown status "NEW"`},
		{name: "dry run", report: `{"files": [{"file_name": "a.go", "mutations": [{"type": "X", "status": "RUNNABLE", "line": 1}]}]}`, want: "is a dry run"},
		{name: "file without a name", report: `{"files": [{"mutations": []}]}`, want: "a file without a name"},
		{name: "mutant without a line", report: `{"files": [{"file_name": "a.go", "mutations": [{"type": "X", "status": "KILLED"}]}]}`, want: "a mutant without a line or a type"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := gittest.New(t)
			r.Commit(map[string]string{"go.mod": goMod})

			_, err := mutation.Check(t.Context(), mutation.Config{Repo: r.Dir, Modules: []string{"."}, Gremlins: fakeGremlins(t, tc.report), Thresholds: thresholdsFile(t)})

			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Errorf("Check() error = %v, want an error that contains %q", err, tc.want)
			}
		})
	}
}

func TestParseThresholds(t *testing.T) {
	t.Parallel()
	tests := []struct {
		input   string
		want    mutation.Thresholds
		wantErr bool
	}{
		{input: `{"efficacy": 80, "mutant_coverage": 92.5}`, want: mutation.Thresholds{Efficacy: 80, MutantCoverage: 92.5}},
		{input: `{"efficacy": 100, "mutant_coverage": 100}`, want: mutation.Thresholds{Efficacy: 100, MutantCoverage: 100}},
		{input: `{"efficacy": 80}`, wantErr: true},
		{input: `{"efficacy": 0, "mutant_coverage": 90}`, wantErr: true},
		{input: `{"efficacy": 80, "mutant_coverage": 100.5}`, wantErr: true},
		{input: `{"efficacy": 80, "mutant_coverage": 90, "extra": 1}`, wantErr: true},
		{input: `{"efficacy": 80, "efficacy": 90, "mutant_coverage": 90}`, wantErr: true},
	}
	for _, tc := range tests {
		got, err := mutation.ParseThresholds([]byte(tc.input))
		if (err != nil) != tc.wantErr || got != tc.want {
			t.Errorf("ParseThresholds(%s) = %+v, %v; want %+v with error %t", tc.input, got, err, tc.want, tc.wantErr)
		}
	}
}

func TestCountsRatios(t *testing.T) {
	t.Parallel()
	c := mutation.Counts{Killed: 3, Lived: 1, NotCovered: 4, TimedOut: 5, NotViable: 6}
	if got, ok := c.Efficacy(); !ok || got != 75 {
		t.Errorf("%+v.Efficacy() = %v, %t; want 75, true", c, got, ok)
	}
	if got, ok := c.MutantCoverage(); !ok || got != 50 {
		t.Errorf("%+v.MutantCoverage() = %v, %t; want 50, true", c, got, ok)
	}
	if got, ok := (mutation.Counts{Killed: 1, Lived: 1}).MutantCoverage(); !ok || got != 100 {
		t.Errorf("Counts{Killed: 1, Lived: 1}.MutantCoverage() = %v, %t; want 100, true", got, ok)
	}
	if _, ok := (mutation.Counts{NotCovered: 1}).Efficacy(); ok {
		t.Error("Counts{NotCovered: 1}.Efficacy() reports a value, want none without killed or lived mutants")
	}
	if _, ok := (mutation.Counts{TimedOut: 1}).MutantCoverage(); ok {
		t.Error("Counts{TimedOut: 1}.MutantCoverage() reports a value, want none without killed, lived, or uncovered mutants")
	}
}

func TestCheckComparesTheThresholdsWithTheBase(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		base    string
		head    string
		want    []string
		wantErr string
	}{
		{name: "raised", base: `{"efficacy": 80, "mutant_coverage": 90}`, head: `{"efficacy": 85, "mutant_coverage": 90}`},
		{name: "equal", base: `{"efficacy": 85, "mutant_coverage": 90}`, head: `{"efficacy": 85, "mutant_coverage": 95}`},
		{
			name: "both lowered",
			base: `{"efficacy": 80, "mutant_coverage": 90}`,
			head: `{"efficacy": 70, "mutant_coverage": 85.5}`,
			want: []string{"thresholds.json: the change lowers a threshold: efficacy 70 < 80, mutant_coverage 85.5 < 90"},
		},
		{name: "invalid base", base: `{"efficacy": 80}`, head: `{"efficacy": 80, "mutant_coverage": 90}`, wantErr: "the base revision of thresholds.json"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := gittest.New(t)
			// loose/main.go has no go.mod above it, so it belongs to no module.
			base := r.Commit(map[string]string{"thresholds.json": tc.base})
			r.Commit(map[string]string{"thresholds.json": tc.head, "loose/main.go": "package main\n"})

			report, err := mutation.Check(t.Context(), mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"."}, Gremlins: "/nonexistent/gremlins", Thresholds: filepath.Join(r.Dir, "thresholds.json")})

			if tc.wantErr != "" {
				if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
					t.Fatalf("Check() error = %v, want an error that contains %q", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("Check() returned error %v", err)
			}
			if diff := cmp.Diff(tc.want, messages(report)); diff != "" {
				t.Errorf("findings mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestCheckPassesTheSettingsAndAddsTheCountsOfEachModule(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	r.Commit(map[string]string{"go.mod": goMod, "sub/go.mod": goMod})
	dir := t.TempDir()
	gremlins := filepath.Join(dir, "gremlins")
	script := "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$(dirname \"$0\")/args.txt\"\ncat > \"$3\" <<'EOF'\n" +
		`{"files": [{"file_name": "a.go", "mutations": [` +
		`{"type": "X", "status": "KILLED", "line": 1}, {"type": "X", "status": "NOT VIABLE", "line": 2}]}]}` + "\nEOF\n"
	writeFile(t, gremlins, script)
	if err := os.Chmod(gremlins, 0o700); err != nil { //nolint:gosec // G302: the fake program needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}

	report := check(t, mutation.Config{Repo: r.Dir, Modules: []string{".", "sub"}, Gremlins: gremlins, Thresholds: thresholdsFile(t), Workers: 3, TimeoutCoefficient: 7})

	if want := (mutation.Counts{Killed: 2, NotViable: 2}); report.Counts != want {
		t.Errorf("Counts = %+v, want %+v from the two modules", report.Counts, want)
	}
	args, err := os.ReadFile(filepath.Join(dir, "args.txt")) //nolint:gosec // G304: the path is in the temporary directory of the test.
	if err != nil {
		t.Fatal(err)
	}
	for line := range strings.SplitSeq(strings.TrimSpace(string(args)), "\n") {
		if !strings.HasSuffix(line, " --workers 3 --timeout-coefficient 7 .") || strings.Contains(line, "--diff") {
			t.Errorf("Gremlins arguments = %q, want --workers 3 --timeout-coefficient 7 and no --diff for a full run", line)
		}
	}
}

func TestCheckDoesNotMutateADeletedFile(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": adultSource("// Adult reports whether age is adult.\n"), "calc/extra.go": "package calc\n"})
	r.Commit(map[string]string{"calc/extra.go": ""})

	report := check(t, mutation.Config{Repo: r.Dir, Base: base, Modules: []string{"."}, Gremlins: "/nonexistent/gremlins", Thresholds: thresholdsFile(t)})

	if len(report.Changed) != 0 || len(report.Mutated) != 0 {
		t.Errorf("Check() changed %q and mutated %q, want neither: a deleted file has no line to mutate", report.Changed, report.Mutated)
	}
}
