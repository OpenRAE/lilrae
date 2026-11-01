package architecture_test

import (
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

// checkPR runs the pull request check from base and returns the findings.
func checkPR(t *testing.T, r *gittest.Repo, base string, issue int, promotion bool) []string {
	t.Helper()
	report, err := architecture.CheckPullRequest(t.Context(), architecture.PRConfig{Repo: r.Dir, Base: base, Issue: issue, Promotion: promotion})
	if err != nil {
		t.Fatalf("CheckPullRequest(base %s, issue %d) returned error %v", base, issue, err)
	}
	return findingStrings(report)
}

// cacheChange adds the package internal/cache to the component values.
func cacheChange() map[string]string {
	return map[string]string{
		"architecture/model.yaml":  strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, internal/cache]", 1),
		"internal/cache/cache.go":  "package cache\n\nimport (\n\t\"fmt\"\n\n\t\"example.com/app/internal/values\"\n)\n\nvar _ = fmt.Sprint(values.X)\n",
		"internal/cache/x_test.go": "package cache\n\nimport (\n\t\"testing\"\n\n\t\"example.com/app/internal/values\"\n)\n\nfunc TestX(t *testing.T) { _ = values.X }\n",
		// An external test package imports its own package.
		"internal/cache/y_test.go":     "package cache_test\n\nimport (\n\t\"testing\"\n\n\t\"example.com/app/internal/cache\"\n)\n\nfunc TestY(t *testing.T) { _ = cache.V }\n",
		"internal/cache/testdata/a.go": "package ignored\n",
	}
}

func TestCheckPullRequestComparesTheCodeWithTheDesign(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		record string
		want   []string
	}{
		{
			name: "matching record",
			record: `design: 1
issue: 7
packages:
  - path: internal/cache
    component: values
    imports: [example.com/app/internal/values]
model_changes: [component:values.packages]
`,
		},
		{
			name: "missing package and model change",
			record: `design: 1
issue: 7
`,
			want: []string{
				`[design-model-changes-differ] docs/architecture/issue-7-cache-design.md: the model changes "component:values.packages" are not in the record`,
				`[design-package-missing] docs/architecture/issue-7-cache-design.md: the change edits the package "internal/cache", which the design record does not list`,
			},
		},
		{
			name: "different imports",
			record: `design: 1
issue: 7
packages:
  - path: internal/cache
    component: values
    test_imports: [example.com/app/internal/values]
model_changes: [component:values.packages]
`,
			want: []string{
				`[design-imports-differ] docs/architecture/issue-7-cache-design.md: the imports of "internal/cache" are "example.com/app/internal/values" and the test imports are none, but the design record lists none and "example.com/app/internal/values"`,
			},
		},
		{
			name: "wrong issue",
			record: `design: 1
issue: 8
packages:
  - path: internal/cache
    component: values
    imports: [example.com/app/internal/values]
model_changes: [component:values.packages]
`,
			want: []string{`[invalid-design] docs/architecture/issue-7-cache-design.md: the design record names issue 8, not issue 7`},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, nil)
			base := r.Git("rev-parse", "HEAD")
			files := cacheChange()
			files["docs/architecture/issue-7-cache-design.md"] = noteFor(tc.record)
			r.Commit(files)

			requireFindings(t, checkPR(t, r, base, 7, false), tc.want)
		})
	}
}

func TestCheckPullRequestRemovedPackages(t *testing.T) {
	t.Parallel()
	removal := map[string]string{
		"architecture/model.yaml":      strings.Replace(strings.Replace(fixtureModel, "    test_uses: [testkit]\n", "", 1), "  - name: testkit\n    layer: core\n    responsibility: Helps tests.\n    packages: [internal/testkit]\n", "", 1),
		"internal/testkit/testkit.go":  "",
		"internal/store/store_test.go": "package store\n\nimport (\n\t\"testing\"\n\n\t\"example.com/check\"\n)\n\nfunc TestX(t *testing.T) { _ = check.W }\n",
	}
	tests := []struct {
		name   string
		files  map[string]string
		record string
		want   []string
	}{
		{
			name:  "removed package without files",
			files: removal,
			record: `design: 1
issue: 7
packages:
  - path: internal/testkit
    removed: true
  - path: internal/store
    component: store
    imports: [example.com/app/internal/values, example.com/dep]
    test_imports: [example.com/check]
model_changes: [component:store.test_uses, component:testkit]
`,
		},
		{
			name:  "removed package that keeps files",
			files: map[string]string{"internal/values/values.go": "package values\n\n// X is a value.\nconst X = 2\n"},
			record: `design: 1
issue: 7
packages:
  - path: internal/values
    removed: true
`,
			want: []string{
				`[design-forbidden] docs/architecture/issue-7-x-design.md: the removed package "internal/values" is still in the component "values"`,
				`[design-imports-differ] docs/architecture/issue-7-x-design.md: the design record removes the package "internal/values", but it has Go files`,
			},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, nil)
			base := r.Git("rev-parse", "HEAD")
			files := map[string]string{"docs/architecture/issue-7-x-design.md": noteFor(tc.record)}
			maps.Copy(files, tc.files)
			r.Commit(files)

			requireFindings(t, checkPR(t, r, base, 7, false), tc.want)
		})
	}
}

func TestCheckPullRequestNeedsADesignNote(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		issue int
		notes map[string]string
		want  []string
	}{
		{name: "no issue", want: []string{"[missing-design] the branch: the change edits Go packages or the model, but the branch names no issue"}},
		{name: "no note", issue: 7, want: []string{"[missing-design] docs/architecture/issue-7-*-design.md: the change edits Go packages or the model, but issue 7 has no tracked design note"}},
		{
			name:  "two notes",
			issue: 7,
			notes: map[string]string{"docs/architecture/issue-7-a-design.md": "# A\n", "docs/architecture/issue-7-b-design.md": "# B\n"},
			want:  []string{"[invalid-design] docs/architecture/issue-7-*-design.md: issue 7 has 2 design notes"},
		},
		{
			name:  "no front matter",
			issue: 7,
			notes: map[string]string{"docs/architecture/issue-7-a-design.md": "# A\n"},
			want:  []string{"[invalid-design] docs/architecture/issue-7-a-design.md: the design note has no design front matter"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, nil)
			base := r.Git("rev-parse", "HEAD")
			files := cacheChange()
			maps.Copy(files, tc.notes)
			r.Commit(files)

			requireFindings(t, checkPR(t, r, base, tc.issue, false), tc.want)
		})
	}
}

func TestCheckPullRequestWithoutAPackageOrModelChangeNeedsNoNote(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)
	base := r.Git("rev-parse", "HEAD")
	r.Commit(map[string]string{"README": "docs\n", "internal/values/testdata/b.go": "package x\n", "third_party/lib/lib.go": "package lib\n", "_head/head.go": "package head\n"})

	if got := checkPR(t, r, base, 0, false); len(got) != 0 {
		t.Errorf("CheckPullRequest() findings = %q, want none for a change without Go packages or model changes", got)
	}
}

func TestCheckPullRequestPromotionSkipsTheComparison(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)
	base := r.Git("rev-parse", "HEAD")
	files := cacheChange()
	files["internal/values/values.go"] = "package values\n\nimport \"example.com/app/internal/store\"\n\nvar _ = store.X\n"
	r.Commit(files)

	got := checkPR(t, r, base, 0, true)

	requireFindings(t, got, []string{`[forbidden-import] internal/values/values.go:3`})
}

func TestCheckPullRequestReportsErrors(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)
	tests := map[string]architecture.PRConfig{
		"unknown base": {Repo: r.Dir, Base: "missing", Issue: 7},
		"outside git":  {Repo: t.TempDir(), Base: "HEAD", Issue: 7},
	}
	for name, cfg := range tests {
		if _, err := architecture.CheckPullRequest(t.Context(), cfg); err == nil {
			t.Errorf("CheckPullRequest(%s) returned no error", name)
		}
	}
	bad := newFixture(t, map[string]string{"docs/architecture/issue-7-a-design.md": noteFor("design: 3\n")})
	base := bad.Git("rev-parse", "HEAD~0")
	bad.Commit(cacheChange())
	if _, err := architecture.CheckPullRequest(t.Context(), architecture.PRConfig{Repo: bad.Dir, Base: base, Issue: 7}); err == nil {
		t.Error("CheckPullRequest(note with version 3) returned no error")
	}
}
