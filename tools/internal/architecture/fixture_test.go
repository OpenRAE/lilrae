package architecture_test

import (
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

// fixtureRules gives a fix-it message for each rule of the checker.
const fixtureRules = `rules:
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

// fixtureModel is a model of the fixture repository.
const fixtureModel = `version: 1
layers:
  - name: entry
    description: Commands.
    may_use: [entry, core]
  - name: core
    description: Values and stores.
    may_use: [core]
components:
  - name: app
    layer: entry
    responsibility: Runs the application.
    packages: [app]
    uses: [values, store]
  - name: values
    layer: core
    responsibility: Holds values.
    packages: [internal/values]
  - name: store
    layer: core
    responsibility: Stores values.
    packages: [internal/store]
    uses: [values]
    modules: [example.com/dep]
    test_uses: [testkit]
    test_modules: [example.com/check]
  - name: testkit
    layer: core
    responsibility: Helps tests.
    packages: [internal/testkit]
public: []
vendored: [third_party]
` + fixtureRules

// fixtureFiles returns the files of a fixture repository that has no finding.
func fixtureFiles() map[string]string {
	return map[string]string{
		"architecture/model.yaml":             fixtureModel,
		"go.mod":                              "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n",
		"app/main.go":                         "package main\n\nimport (\n\t\"fmt\"\n\n\t\"example.com/app/internal/store\"\n\t\"example.com/app/internal/values\"\n)\n\nfunc main() { fmt.Println(store.X, values.X) }\n",
		"internal/values/values.go":           "// Package values holds values.\npackage values\n\n// X is a value.\nconst X = 1\n",
		"internal/store/store.go":             "package store\n\nimport (\n\t\"example.com/app/internal/values\"\n\t\"example.com/dep/sub\"\n)\n\nvar _ = sub.Y\n\n// X is a value.\nconst X = values.X\n",
		"internal/store/store_test.go":        "package store\n\nimport (\n\t\"testing\"\n\n\t\"example.com/app/internal/testkit\"\n\t\"example.com/check\"\n)\n\nfunc TestX(t *testing.T) { _, _ = testkit.Z, check.W }\n",
		"internal/testkit/testkit.go":         "package testkit\n\n// Z is a value.\nconst Z = 3\n",
		"internal/values/testdata/fixture.go": "package broken {\n",
		"third_party/lib/go.mod":              "module example.com/lib\n\ngo 1.27.0\n",
		"third_party/lib/lib.go":              "package lib\n\nimport \"example.com/forbidden\"\n",
	}
}

// newFixture returns a repository with the fixture files changed by files,
// where an empty content deletes a file.
func newFixture(t *testing.T, files map[string]string) *gittest.Repo {
	t.Helper()
	all := fixtureFiles()
	for name, content := range files {
		if content == "" {
			delete(all, name)
			continue
		}
		all[name] = content
	}
	r := gittest.New(t)
	r.Commit(all)
	return r
}

// check runs the repository check and returns the findings as strings.
func check(t *testing.T, r *gittest.Repo) []string {
	t.Helper()
	report, err := architecture.Check(t.Context(), r.Dir)
	if err != nil {
		t.Fatalf("Check() returned error %v", err)
	}
	return findingStrings(report)
}

// findingStrings returns the findings of a report as strings.
func findingStrings(report architecture.Report) []string {
	var out []string
	for _, f := range report.Findings {
		out = append(out, f.String())
	}
	return out
}

// requireFindings fails the test unless got has one finding for each entry of
// want, in order, that starts with the entry and ends with the fix-it message
// of its rule in the fixture model.
func requireFindings(t *testing.T, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("findings = %q, want %d findings that start with %q", got, len(want), want)
	}
	for i := range want {
		if !strings.HasPrefix(got[i], want[i]) {
			t.Errorf("finding %d = %q, want it to start with %q", i, got[i], want[i])
		}
		rule, _, _ := strings.Cut(strings.TrimPrefix(got[i], "["), "]")
		if fix := "\n    fix: Fix " + rule + "."; !strings.HasSuffix(got[i], fix) {
			t.Errorf("finding %d = %q, want the fix-it message %q", i, got[i], fix)
		}
	}
}
