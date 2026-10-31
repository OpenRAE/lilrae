package architecture_test

import (
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

// noteFor returns a design note with front matter.
func noteFor(front string) string {
	return "---\n" + front + "---\n\n# Design\n"
}

// checkDesign runs the design check of note against base and returns the
// findings.
func checkDesign(t *testing.T, r *gittest.Repo, base, note string) []string {
	t.Helper()
	report, err := architecture.CheckDesign(t.Context(), r.Dir, base, note)
	if err != nil {
		t.Fatalf("CheckDesign(%s) returned error %v", note, err)
	}
	return findingStrings(report)
}

func TestCheckDesignAcceptsARecordThatTheModelPermits(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)
	base := r.Git("rev-parse", "HEAD")
	model := strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, internal/cache]", 1)
	r.Commit(map[string]string{
		"architecture/model.yaml": model,
		"docs/issue-7-design.md": noteFor(`design: 1
issue: 7
packages:
  - path: internal/cache
    component: values
model_changes:
  - component:values.packages
`),
	})

	if got := checkDesign(t, r, base, "docs/issue-7-design.md"); len(got) != 0 {
		t.Errorf("CheckDesign() findings = %q, want none", got)
	}
}

func TestCheckDesignRejectsABrokenRecord(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		record string
		want   []string
	}{
		{
			name: "forbidden imports",
			record: `design: 1
issue: 7
packages:
  - path: internal/values
    component: values
    imports: [example.com/app/internal/store, example.com/dep, fmt]
    test_imports: [example.com/app/internal/testkit, Not A Module, example.com/app/internal/nowhere]
`,
			want: []string{
				`[design-forbidden] docs/issue-7-design.md: the package "internal/values" imports "example.com/app/internal/store" in "store", which "values" does not use`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/values" imports the module "example.com/dep", which "values" may not import`,
				`[invalid-design] docs/issue-7-design.md: the package "internal/values" lists the standard library import "fmt"; leave it out`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/values" imports "example.com/app/internal/testkit" in "testkit", which "values" does not use`,
				`[invalid-design] docs/issue-7-design.md: the import "Not A Module" of "internal/values" is not a valid module path`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/values" imports "example.com/app/internal/nowhere", which is in no component`,
			},
		},
		{
			name: "test permissions in production imports",
			record: `design: 1
issue: 7
packages:
  - path: internal/store
    component: store
    imports: [example.com/app/internal/testkit, example.com/check]
    test_imports: [example.com/app/internal/testkit, example.com/check]
`,
			want: []string{
				`[invalid-design] docs/issue-7-design.md: the imports of "internal/store" list "example.com/app/internal/testkit" twice`,
				`[invalid-design] docs/issue-7-design.md: the imports of "internal/store" list "example.com/check" twice`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/store" imports "example.com/app/internal/testkit" in "testkit", which "store" does not use`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/store" imports the module "example.com/check", which "store" may not import`,
			},
		},
		{
			name: "unknown component and wrong package",
			record: `design: 1
issue: 7
packages:
  - path: internal/new
    component: nowhere
  - path: internal/other
    component: values
  - path: ../escape
    component: values
  - path: internal/other
    component: values
`,
			want: []string{
				`[design-forbidden] docs/issue-7-design.md: the package "internal/new" is in the unknown component "nowhere"`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/other" is not in the packages of "values"`,
				`[invalid-design] docs/issue-7-design.md: the package path "../escape" is not a clean relative path`,
				`[design-forbidden] docs/issue-7-design.md: the package "../escape" is not in the packages of "values"`,
				`[invalid-design] docs/issue-7-design.md: the package "internal/other" is listed twice`,
				`[design-forbidden] docs/issue-7-design.md: the package "internal/other" is not in the packages of "values"`,
			},
		},
		{
			name: "removed packages",
			record: `design: 1
issue: 7
packages:
  - path: internal/values
    component: values
    removed: true
    imports: [example.com/dep]
  - path: internal/gone
    removed: true
`,
			want: []string{
				`[invalid-design] docs/issue-7-design.md: the removed package "internal/values" lists imports`,
				`[design-forbidden] docs/issue-7-design.md: the removed package "internal/values" is still in the component "values"`,
			},
		},
		{
			name: "model changes",
			record: `design: 1
issue: 0
model_changes: [layers, layers, component:Bad, rules]
`,
			want: []string{
				`[invalid-design] docs/issue-7-design.md: the design record names the issue 0, which is not a positive number`,
				`[invalid-design] docs/issue-7-design.md: the model change "component:Bad" is not layers, public, rules, vendored, or component:<name>[.<field>]`,
				`[invalid-design] docs/issue-7-design.md: the model changes list "layers" twice`,
				`[design-model-changes-differ] docs/issue-7-design.md: the record lists the model changes "component:Bad", "layers", "rules", which did not change`,
			},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, map[string]string{"docs/issue-7-design.md": noteFor(tc.record)})

			requireFindings(t, checkDesign(t, r, "HEAD", "docs/issue-7-design.md"), tc.want)
		})
	}
}

func TestCheckDesignComparesTheModelChangesWithTheBase(t *testing.T) {
	t.Parallel()
	edits := []struct {
		old, replacement string
		change           string
	}{
		{"description: Commands.", "description: Entry points.", "layers"},
		{"public: []", "public: [internal/values]", "public"},
		{"Fix stale-diagram.", "Run the diagram command.", "rules"},
		{"vendored: [third_party]", "vendored: [third_party, extra]", "vendored"},
		{"    layer: core\n    responsibility: Holds values.", "    layer: entry\n    responsibility: Holds values.", "component:values.layer"},
		{"responsibility: Holds values.", "responsibility: Keeps values.", "component:values.responsibility"},
		{"packages: [internal/values]", "packages: [internal/values, internal/extra]", "component:values.packages"},
		{"uses: [values]\n", "uses: [values, testkit]\n", "component:store.uses"},
		{"modules: [example.com/dep]", "modules: [example.com/dep, example.com/more]", "component:store.modules"},
		{"test_uses: [testkit]", "test_uses: [testkit, app]", "component:store.test_uses"},
		{"test_modules: [example.com/check]", "test_modules: [example.com/check, example.com/more]", "component:store.test_modules"},
		{"  - name: testkit\n", "  - name: kit\n", "component:kit"},
	}
	for _, e := range edits {
		t.Run(e.change, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, nil)
			base := r.Git("rev-parse", "HEAD")
			commitModel(r, strings.Replace(fixtureModel, e.old, e.replacement, 1))
			r.Commit(map[string]string{"docs/issue-7-design.md": noteFor("design: 1\nissue: 7\nmodel_changes: []\n")})

			got := checkDesign(t, r, base, "docs/issue-7-design.md")

			found := false
			for _, finding := range got {
				if strings.HasPrefix(finding, "[design-model-changes-differ]") && strings.Contains(finding, `"`+e.change+`"`) {
					found = true
				}
			}
			if !found {
				t.Errorf("CheckDesign() findings = %q, want a model change finding that names %q", got, e.change)
			}
		})
	}
}

func TestCheckDesignTreatsAMissingBaseModelAsEmpty(t *testing.T) {
	t.Parallel()
	r := gittest.New(t)
	base := r.Commit(map[string]string{"README": "empty\n"})
	files := fixtureFiles()
	files["docs/issue-7-design.md"] = noteFor(`design: 1
issue: 7
model_changes: [layers, rules, vendored, component:app, component:store, component:testkit, component:values]
`)
	r.Commit(files)

	if got := checkDesign(t, r, base, filepath.Join(r.Dir, "docs", "issue-7-design.md")); len(got) != 0 {
		t.Errorf("CheckDesign() findings = %q, want none: each part of a new model is a change", got)
	}
}

func TestCheckDesignRejectsAnUnusableRecord(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		note string
		file string
		base string
		want string
	}{
		{name: "malformed front matter", note: noteFor("design: [\n"), want: "decode the YAML document"},
		{name: "wrong version", note: noteFor("design: 2\nissue: 7\n"), want: "the design record version must be 1"},
		{name: "unknown field", note: noteFor("design: 1\nissue: 7\nowner: me\n"), want: "field owner not found"},
		{name: "outside the working tree", file: "../note.md", want: "is not in the working tree"},
		{name: "missing note", file: "docs/none.md", want: "read the design note"},
		{name: "unknown base", base: "missing", want: `resolve "missing" to a commit`},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			note := tc.note
			if note == "" {
				note = noteFor("design: 1\nissue: 7\n")
			}
			r := newFixture(t, map[string]string{"docs/issue-7-design.md": note})
			file, base := tc.file, tc.base
			if file == "" {
				file = "docs/issue-7-design.md"
			}
			if base == "" {
				base = "HEAD"
			}

			_, err := architecture.CheckDesign(t.Context(), r.Dir, base, file)

			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Errorf("CheckDesign() error = %v, want an error that contains %q", err, tc.want)
			}
		})
	}
}

func TestCheckDesignReportsANoteWithoutFrontMatter(t *testing.T) {
	t.Parallel()
	for name, note := range map[string]string{"no opening": "# Design\n", "no closing": "---\ndesign: 1\n"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, map[string]string{"docs/issue-7-design.md": note})

			got := checkDesign(t, r, "HEAD", "docs/issue-7-design.md")

			requireFindings(t, got, []string{"[invalid-design] docs/issue-7-design.md: the design note has no design front matter"})
		})
	}
}
