package regression_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/lilrae/tools/internal/gittest"
	"github.com/OpenRAE/lilrae/tools/internal/regression"
)

const goMod = "module example.com/fixture\n\ngo 1.27.0\n"

// valueSource returns a package calc whose Value returns v.
func valueSource(v string) string {
	return "// Package calc is a fixture.\npackage calc\n\n// Value returns a number.\nfunc Value() int { return " + v + " }\n"
}

// valueTest returns a test file with a test that wants Value to return 2.
// doc is the doc comment of the test, and body runs before the comparison.
func valueTest(doc, body string) string {
	return "package calc\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nvar _ = os.Exit\n\n" +
		doc + "func TestValue(t *testing.T) {\n" + body + "\tif got := Value(); got != 2 {\n\t\tt.Fatalf(\"Value() = %d, want 2\", got)\n\t}\n}\n"
}

// repo is a fixture repository for the check.
type repo struct {
	*gittest.Repo

	t *testing.T
}

func newRepo(t *testing.T) *repo {
	t.Helper()
	return &repo{Repo: gittest.New(t), t: t}
}

// check runs the check from base to HEAD and returns the report.
func (r *repo) check(base string, issue int, bug bool) regression.Report {
	r.t.Helper()
	report, err := regression.Check(r.t.Context(), regression.Config{Repo: r.Dir, Base: base, Issue: issue, Bug: bug})
	if err != nil {
		r.t.Fatalf("Check(base %s, issue %d, bug %t) returned error %v", base, issue, bug, err)
	}
	return report
}

// messages returns the findings as strings.
func messages(report regression.Report) []string {
	var out []string
	for _, f := range report.Findings {
		out = append(out, f.String())
	}
	return out
}

// requireOneFinding fails the test unless report has one finding that
// contains want.
func requireOneFinding(t *testing.T, report regression.Report, want string) {
	t.Helper()
	got := messages(report)
	if len(got) != 1 || !strings.Contains(got[0], want) {
		t.Fatalf("findings = %q, want one finding that contains %q", got, want)
	}
}

func TestCheckPassesATestThatFailsOnTheBaseAndPassesOnTheHead(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go":      valueSource("2"),
		"calc/calc_test.go": valueTest("// TestValue checks the fix.\n//\n// regression: #7\n", ""),
	})

	report := r.check(base, 7, true)

	if got := messages(report); len(got) != 0 {
		t.Errorf("findings = %q, want none", got)
	}
	want := []regression.Test{{File: "calc/calc_test.go", Name: "TestValue"}}
	if diff := cmp.Diff(want, report.Selected); diff != "" {
		t.Errorf("Selected mismatch (-want +got):\n%s", diff)
	}
}

func TestCheckRejectsATestThatDoesNotFailOnTheBase(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		body string
		want string
	}{
		{name: "passes", body: "\tif Value() == 1 {\n\t\treturn\n\t}\n", want: "TestValue: the test passed on the base revision; it must fail there"},
		{name: "skipped", body: "\tif Value() == 1 {\n\t\tt.Skip(\"base\")\n\t}\n", want: "TestValue: the test was skipped on the base revision"},
		{name: "exits", body: "\tif Value() == 1 {\n\t\tos.Exit(3)\n\t}\n", want: "TestValue: the test did not finish on the base revision"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newRepo(t)
			base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
			r.Commit(map[string]string{
				"calc/calc.go":      valueSource("2"),
				"calc/calc_test.go": valueTest("// regression: #7\n", tc.body),
			})

			requireOneFinding(t, r.check(base, 7, false), tc.want)
		})
	}
}

func TestCheckRejectsATestThatDoesNotBuildOnTheBase(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go": valueSource("2") + "\n// Twice returns two times Value.\nfunc Twice() int { return 2 * Value() }\n",
		"calc/calc_test.go": "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestTwice(t *testing.T) {\n" +
			"\tif got := Twice(); got != 4 {\n\t\tt.Fatalf(\"Twice() = %d, want 4\", got)\n\t}\n}\n",
	})

	requireOneFinding(t, r.check(base, 7, false), "TestTwice: the test does not build on the base revision; a regression test must use the API of the base revision: ")
	requireOneFinding(t, r.check(base, 7, false), "undefined: Twice")
}

func TestCheckRejectsATestThatFailsOnTheHead(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go":      valueSource("3"),
		"calc/calc_test.go": valueTest("// regression: #7\n", ""),
	})

	requireOneFinding(t, r.check(base, 7, false), "TestValue: the test failed on the head revision; it must pass there")
}

func TestCheckReplaysOnlyAddedOrChangedTestsForTheIssue(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	unchanged := "\n// regression: #7\nfunc TestUnchanged(t *testing.T) {}\n"
	base := r.Commit(map[string]string{
		"go.mod":            goMod,
		"calc/calc.go":      valueSource("1"),
		"calc/old_test.go":  "package calc\n\nimport \"testing\"\n" + unchanged,
		"calc/edit_test.go": "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestEdited(t *testing.T) {}\n",
	})
	r.Commit(map[string]string{
		"calc/calc.go": valueSource("2"),
		// The unchanged test moves to another file of the same package.
		"calc/old_test.go":   "",
		"calc/moved_test.go": "package calc\n\nimport \"testing\"\n" + unchanged,
		"calc/edit_test.go":  valueTest("// regression: #7\n", "") + "\n// regression: #8\nfunc TestOtherIssue(t *testing.T) {}\n",
	})

	report := r.check(base, 7, false)

	want := []regression.Test{{File: "calc/edit_test.go", Name: "TestValue"}}
	if diff := cmp.Diff(want, report.Selected); diff != "" {
		t.Errorf("Selected mismatch (-want +got):\n%s", diff)
	}
	if got := messages(report); len(got) != 0 {
		t.Errorf("findings = %q, want none", got)
	}
}

func TestCheckReplaysWithTheHeadTestFilesAndTestData(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	readWant := "package calc\n\nimport (\n\t\"os\"\n\t\"strconv\"\n\t\"strings\"\n\t\"testing\"\n)\n\n" +
		"// wantValue reads the wanted value from the test data.\nfunc wantValue(t *testing.T) int {\n\tt.Helper()\n" +
		"\tdata, err := os.ReadFile(\"testdata/want.txt\")\n\tif err != nil {\n\t\tt.Fatal(err)\n\t}\n" +
		"\tv, err := strconv.Atoi(strings.TrimSpace(string(data)))\n\tif err != nil {\n\t\tt.Fatal(err)\n\t}\n\treturn v\n}\n"
	base := r.Commit(map[string]string{
		"go.mod":                 goMod,
		"calc/calc.go":           valueSource("1"),
		"calc/testdata/want.txt": "1\n",
		"calc/helper_test.go":    readWant,
	})
	r.Commit(map[string]string{
		"calc/calc.go":           valueSource("2"),
		"calc/testdata/want.txt": "2\n",
		// The helper moves to a file with another name.
		"calc/helper_test.go": "",
		"calc/want_test.go":   readWant,
		"calc/calc_test.go": "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestValue(t *testing.T) {\n" +
			"\tif got, want := Value(), wantValue(t); got != want {\n\t\tt.Fatalf(\"Value() = %d, want %d\", got, want)\n\t}\n}\n",
	})

	report := r.check(base, 7, false)

	if got := messages(report); len(got) != 0 {
		t.Errorf("findings = %q, want none: the base run must use the head test data and must not keep deleted test files", got)
	}
}

func TestCheckFindsTheModuleOfANestedPackage(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"README": "fixture\n", "sub/go.mod": goMod, "sub/calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"sub/calc/calc.go":      valueSource("2"),
		"sub/calc/calc_test.go": valueTest("// regression: #7\n", ""),
	})

	report := r.check(base, 7, false)

	if got := messages(report); len(got) != 0 {
		t.Errorf("findings = %q, want none", got)
	}
}

func TestCheckRequiresARegressionTestForABugFix(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		bug   bool
		want  []string
	}{
		{
			name:  "bug fix without a test",
			files: map[string]string{"calc/calc.go": valueSource("2")},
			bug:   true,
			want:  []string{"issue #7: the issue has the bug label and the change edits Go production code, but the change adds or changes no test with \"regression: #7\""},
		},
		{
			name:  "bug fix that only deletes a production file",
			files: map[string]string{"calc/extra.go": ""},
			bug:   true,
			want:  []string{"issue #7: the issue has the bug label and the change edits Go production code, but the change adds or changes no test with \"regression: #7\""},
		},
		{name: "change without the bug label", files: map[string]string{"calc/calc.go": valueSource("2")}},
		{name: "bug without a production change", files: map[string]string{"calc/notes_test.go": "package calc\n"}, bug: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newRepo(t)
			base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1"), "calc/extra.go": "package calc\n"})
			r.Commit(tc.files)

			if diff := cmp.Diff(tc.want, messages(r.check(base, 7, tc.bug))); diff != "" {
				t.Errorf("findings mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestCheckIgnoresThePathsThatTheGoCommandIgnores(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		want  []string
	}{
		{
			name: "production files",
			files: map[string]string{
				"_scratch/scratch.go": "package scratch\n",
				".hidden/hidden.go":   "package hidden\n",
				"calc/_old.go":        "package calc\n",
				"calc/.new.go":        "package calc\n",
				"calc/testdata/x.go":  "package x\n",
			},
		},
		{
			name:  "regression test",
			files: map[string]string{"calc/calc.go": valueSource("2"), "calc/_value_test.go": valueTest("// regression: #7\n", "")},
			want:  []string{"issue #7: the issue has the bug label and the change edits Go production code, but the change adds or changes no test with \"regression: #7\""},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newRepo(t)
			base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
			r.Commit(tc.files)

			report := r.check(base, 7, true)

			if diff := cmp.Diff(tc.want, messages(report)); diff != "" {
				t.Errorf("findings mismatch (-want +got):\n%s", diff)
			}
			if len(report.Selected) != 0 {
				t.Errorf("Check() replayed %v, want no test from an ignored path", report.Selected)
			}
		})
	}
}

func TestCheckReplaysATestThatLeavesAnIgnoredFile(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	test := valueTest("// regression: #7\n", "")
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1"), "calc/_value_test.go": "package calc\n\nimport \"testing\"\n\n//regression broken\nfunc TestValue(t *testing.T) {"})
	r.Commit(map[string]string{"calc/calc.go": valueSource("2"), "calc/_value_test.go": "", "calc/value_test.go": test})
	baseWithTest := r.Commit(map[string]string{"calc/calc.go": valueSource("1"), "calc/value_test.go": "", "calc/_value_test.go": test})
	r.Commit(map[string]string{"calc/calc.go": valueSource("2"), "calc/_value_test.go": "", "calc/value_test.go": test})

	for _, from := range []string{baseWithTest, base} {
		report := r.check(from, 7, false)

		want := []regression.Test{{File: "calc/value_test.go", Name: "TestValue"}}
		if diff := cmp.Diff(want, report.Selected); diff != "" || len(report.Findings) != 0 {
			t.Errorf("Check(base %s) selected mismatch (-want +got):\n%s\nfindings: %q", from, diff, messages(report))
		}
	}
}

// TestCheckRejectsATestNameInBothTestPackages declares TestValue in the
// package and in its external test package. The marked internal test passes
// on both revisions, and the external test fails on the base revision, so a
// replay by name could credit the wrong test.
func TestCheckRejectsATestNameInBothTestPackages(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go":      valueSource("2"),
		"calc/calc_test.go": "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestValue(t *testing.T) {}\n",
		"calc/ext_test.go": "package calc_test\n\nimport (\n\t\"testing\"\n\n\t\"example.com/fixture/calc\"\n)\n\n" +
			"func TestValue(t *testing.T) {\n\tif got := calc.Value(); got != 2 {\n\t\tt.Fatalf(\"Value() = %d, want 2\", got)\n\t}\n}\n",
	})

	report := r.check(base, 7, false)

	requireOneFinding(t, report, "TestValue: the package and its external test package both declare TestValue, so the replay cannot tell their results apart; rename one")
	if len(report.Selected) != 0 {
		t.Errorf("Check() replayed %v, want no test with an ambiguous name", report.Selected)
	}
}

func TestCheckValidatesTheRegressionComments(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{"calc/calc_test.go": "package calc\n\nimport \"testing\"\n\n" +
		"// regression: 12\nfunc TestMalformed(t *testing.T) {}\n\n" +
		"//regression:#13\nfunc TestNoSpace(t *testing.T) {}\n\n" +
		"// regression: #14\nfunc helper() {}\n\n" +
		"// regression: #15\n\nfunc TestDetached(t *testing.T) {}\n\n" +
		"/*\nregression: #16\nregression: #17\n*/\nfunc TestTwo(t *testing.T) {}\n\n" +
		"// regression: #18\nfunc Testlower(t *testing.T) {}\n\n" +
		"// A regression: #19 here is prose.\nfunc TestProse(t *testing.T) {}\n\n" +
		"/*\nTestBlock has a malformed line.\nregression: #x\n*/\nfunc TestBlock(t *testing.T) {}\n\n" +
		"// regression: #99999999999999999999\nfunc TestHuge(t *testing.T) {}\n",
	})

	got := messages(r.check(base, 0, false))

	want := []string{
		"calc/calc_test.go:5: malformed regression comment \"regression: 12\"; write \"regression: #<issue>\"",
		"calc/calc_test.go:8: malformed regression comment \"regression:#13\"; write \"regression: #<issue>\"",
		"calc/calc_test.go:11: the regression comment is not in the doc comment of a test function",
		"calc/calc_test.go:14: the regression comment is not in the doc comment of a test function",
		"calc/calc_test.go:24: the regression comment is not in the doc comment of a test function",
		"calc/calc_test.go:32: malformed regression comment \"regression: #x\"; write \"regression: #<issue>\"",
		"calc/calc_test.go:36: malformed issue number in \"regression: #99999999999999999999\"",
		"calc/calc_test.go:22: TestTwo has more than one regression comment",
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("findings mismatch (-want +got):\n%s", diff)
	}
}

func TestCheckWithoutAnIssueReplaysNothing(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go":      valueSource("2"),
		"calc/calc_test.go": valueTest("// regression: #7\n", ""),
	})

	report := r.check(base, 0, true)

	if len(report.Selected) != 0 || len(report.Findings) != 0 {
		t.Errorf("Check(issue 0) selected %v with findings %q, want no selection and no finding", report.Selected, messages(report))
	}
}

func TestCheckReportsAnInvalidBaseRevision(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	r.Commit(map[string]string{"go.mod": goMod})

	_, err := regression.Check(t.Context(), regression.Config{Repo: r.Dir, Base: "--output=x", Issue: 7})

	if err == nil {
		t.Fatal("Check(base \"--output=x\") returned no error, want an error for a revision that names no commit")
	}
}

func TestCheckRejectsATestThatDoesNotRunOrHasNoModule(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		base  map[string]string
		head  map[string]string
		wants []string
	}{
		{
			name: "missing dependency",
			base: map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")},
			head: map[string]string{"calc/calc_test.go": "package calc\n\nimport (\n\t\"testing\"\n\n\t\"example.com/missing\"\n)\n\n" +
				"// regression: #7\nfunc TestValue(t *testing.T) { missing.Run() }\n"},
			wants: []string{"TestValue: the test does not build on the base revision", "TestValue: the test does not build on the head revision"},
		},
		{
			name: "build tag",
			base: map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")},
			head: map[string]string{"calc/calc_test.go": "//go:build fixture\n\n" + valueTest("// regression: #7\n", "")},
			wants: []string{"TestValue: the test did not run on the base revision; it must fail there",
				"TestValue: the test did not run on the head revision; it must pass there"},
		},
		{
			name:  "no module on the base revision",
			base:  map[string]string{"README": "fixture\n"},
			head:  map[string]string{"go.mod": goMod, "calc.go": valueSource("2"), "calc_test.go": valueTest("// regression: #7\n", "")},
			wants: []string{"calc_test.go: TestValue: the package has no Go module on the base revision"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newRepo(t)
			base := r.Commit(tc.base)
			r.Commit(tc.head)

			got := messages(r.check(base, 7, false))

			if len(got) != len(tc.wants) {
				t.Fatalf("findings = %q, want %d findings that contain %q", got, len(tc.wants), tc.wants)
			}
			for i, want := range tc.wants {
				if !strings.Contains(got[i], want) {
					t.Errorf("finding %d = %q, want it to contain %q", i, got[i], want)
				}
			}
		})
	}
}

func TestCheckReplaysAPackageAtTheModuleRootWithSymlinksAndScripts(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc.go": valueSource("1")})
	if err := os.MkdirAll(filepath.Join(r.Dir, "testdata"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(r.Dir, "testdata", "run.sh"), []byte("#!/bin/sh\n"), 0o700); err != nil { //nolint:gosec // G306: the script needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}
	if err := os.Symlink("want.txt", filepath.Join(r.Dir, "testdata", "link.txt")); err != nil {
		t.Fatal(err)
	}
	r.Commit(map[string]string{
		"calc.go":           valueSource("2"),
		"testdata/want.txt": "2\n",
		"calc_test.go": "package calc\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\n// regression: #7\nfunc TestValue(t *testing.T) {\n" +
			"\t// Without the head test data, the test returns early and passes on the base revision.\n" +
			"\tinfo, err := os.Stat(\"testdata/run.sh\")\n\tif err != nil || info.Mode()&0o100 == 0 {\n\t\treturn\n\t}\n" +
			"\tif target, err := os.Readlink(\"testdata/link.txt\"); err != nil || target != \"want.txt\" {\n\t\treturn\n\t}\n" +
			"\tif Value() != 2 {\n\t\tt.Fatal(\"Value() != 2\")\n\t}\n}\n",
	})

	report := r.check(base, 7, false)

	if got := messages(report); len(got) != 0 {
		t.Errorf("findings = %q, want none: the base run needs the head symlink and executable test data", got)
	}
}

// regression: #1554
func TestCheckRejectsAPassingTestWhoseTestBinaryFails(t *testing.T) {
	t.Parallel()
	r := newRepo(t)
	base := r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")})
	r.Commit(map[string]string{
		"calc/calc.go":      valueSource("2"),
		"calc/calc_test.go": valueTest("// regression: #7\n", ""),
		"calc/main_test.go": "package calc\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nfunc TestMain(m *testing.M) {\n\tm.Run()\n\tos.Exit(1)\n}\n",
	})

	report := r.check(base, 7, false)

	requireOneFinding(t, report, "TestValue: the test passed, but the go test command failed on the head revision; it must pass there")
}

func TestCheckQuotesAtMostFiveLinesOfBuildOutput(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		base map[string]string
		test string
		want string
	}{
		{
			name: "compiler errors",
			base: map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("1")},
			test: "package calc\n\nimport \"testing\"\n\n// regression: #7\nfunc TestValue(t *testing.T) {\n" +
				"\t_, _, _, _, _, _, _ = a1, a2, a3, a4, a5, a6, a7\n\tif Value() != 2 {\n\t\tt.Fatal(\"Value() != 2\")\n\t}\n}\n",
			want: "undefined: a",
		},
		{
			name: "invalid go.mod",
			base: map[string]string{"go.mod": goMod + "bogus directive\n", "calc/calc.go": valueSource("1")},
			test: valueTest("// regression: #7\n", ""),
			want: "go.mod",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newRepo(t)
			base := r.Commit(tc.base)
			r.Commit(map[string]string{"go.mod": goMod, "calc/calc.go": valueSource("2"), "calc/calc_test.go": tc.test})

			got := messages(r.check(base, 7, false))

			if len(got) == 0 || !strings.Contains(got[0], "does not build on the base revision") || !strings.Contains(got[0], tc.want) {
				t.Fatalf("findings = %q, want a build finding for the base revision that quotes %q", got, tc.want)
			}
			if _, quoted, _ := strings.Cut(got[0], "base revision: "); strings.Count(quoted, "; ") > 4 {
				t.Errorf("finding %q quotes more than five lines of build output", got[0])
			}
		})
	}
}
