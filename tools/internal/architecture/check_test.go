package architecture_test

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
	"github.com/OpenRAE/lilrae/tools/internal/gittest"
)

func TestCheckPassesTheFixture(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)

	if got := check(t, r); len(got) != 0 {
		t.Errorf("Check() findings = %q, want none for a repository that follows its model", got)
	}
}

func TestCheckRules(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		want  []string
	}{
		{
			name:  "unassigned package",
			files: map[string]string{"internal/extra/extra.go": "package extra\n"},
			want:  []string{`[unassigned-package] internal/extra: the package "internal/extra" is in no component` + "\n    fix: Fix unassigned-package."},
		},
		{
			name:  "stale package",
			files: map[string]string{"internal/testkit/testkit.go": "", "internal/store/store_test.go": ""},
			want:  []string{`[stale-package] architecture/model.yaml:27: the package "internal/testkit" of "testkit" has no Go file`},
		},
		{
			name:  "forbidden import between components",
			files: map[string]string{"internal/values/values.go": "package values\n\nimport \"example.com/app/internal/store\"\n\nvar _ = store.X\n"},
			want:  []string{`[forbidden-import] internal/values/values.go:3: the import "example.com/app/internal/store" is in "store", which "values" does not use`},
		},
		{
			name:  "test use in a production file",
			files: map[string]string{"internal/store/extra.go": "package store\n\nimport \"example.com/app/internal/testkit\"\n\nvar _ = testkit.Z\n"},
			want:  []string{`[forbidden-import] internal/store/extra.go:3: the import "example.com/app/internal/testkit" is in "testkit", which "store" does not use`},
		},
		{
			name:  "forbidden module",
			files: map[string]string{"internal/values/values.go": "package values\n\nimport \"example.com/dep/sub\"\n\nvar _ = sub.Y\n"},
			want:  []string{`[forbidden-module] internal/values/values.go:3: the import "example.com/dep/sub" is in the module "example.com/dep", which "values" may not import`},
		},
		{
			name:  "test module in a production file",
			files: map[string]string{"internal/store/extra.go": "package store\n\nimport \"example.com/check\"\n\nvar _ = check.W\n"},
			want:  []string{`[forbidden-module] internal/store/extra.go:3: the import "example.com/check" is in the module "example.com/check", which "store" may not import`},
		},
		{
			name:  "unrequired module",
			files: map[string]string{"internal/values/values.go": "package values\n\nimport \"example.com/missing/x\"\n\nvar _ = x.Y\n"},
			want:  []string{`[unresolved-import] internal/values/values.go:3: the import "example.com/missing/x" resolves to no first-party package, standard library package, or required module`},
		},
		{
			name:  "invalid import path",
			files: map[string]string{"internal/values/values.go": "package values\n\nimport \"not a path\"\n"},
			want:  []string{`[unresolved-import] internal/values/values.go:3: the import "not a path" resolves to no first-party package, standard library package, or required module`},
		},
		{
			name:  "first-party package without Go files",
			files: map[string]string{"app/main.go": "package main\n\nimport _ \"example.com/app/internal/absent\"\n\nfunc main() {}\n"},
			want:  []string{`[unresolved-import] app/main.go:3: the import "example.com/app/internal/absent" names a first-party package that has no Go file`},
		},
		{
			name: "importable package outside internal",
			files: map[string]string{
				"architecture/model.yaml": strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, api]", 1),
				"api/api.go":              "// Package api is public.\npackage api\n",
			},
			want: []string{`[undeclared-public-package] api: the package "api" can be imported, but it is not under internal/ and not public`},
		},
		{
			name: "replacement with test data",
			files: map[string]string{
				"go.mod":                  "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/dep => ./testdata/dep\n",
				"testdata/dep/go.mod":     "module example.com/dep\n\ngo 1.27.0\n",
				"testdata/dep/sub/sub.go": "package sub\n",
			},
			want: []string{`[undeclared-replacement] go.mod:10: the module "example.com/dep" is replaced with the directory "testdata/dep", which is not a vendored directory`},
		},
		{
			name:  "replacement outside the repository",
			files: map[string]string{"go.mod": "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/dep => ../dep\n"},
			want:  []string{`[undeclared-replacement] go.mod:10: the module "example.com/dep" is replaced with the directory "../dep", which is not a vendored directory`},
		},
		{
			// An absolute path must not become the relative vendored path.
			name:  "absolute replacement that resembles a vendored directory",
			files: map[string]string{"go.mod": "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/dep => /third_party/dep\n"},
			want:  []string{`[undeclared-replacement] go.mod:10: the module "example.com/dep" is replaced with the directory "/third_party/dep", which is not a vendored directory`},
		},
		{
			name: "absolute replacement that resembles a first-party directory",
			files: map[string]string{
				"go.mod":     "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/app/sub => /sub\n",
				"sub/go.mod": "module example.com/app/sub\n\ngo 1.27.0\n",
			},
			want: []string{`[undeclared-replacement] go.mod:10: the first-party module "example.com/app/sub" is replaced with something other than its directory "sub"`},
		},
		{
			// The build would use the code of example.com/app/sub for
			// example.com/dep, which the model checks as a module.
			name: "replacement with another first-party module",
			files: map[string]string{
				"go.mod":     "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/dep => ./sub\n",
				"sub/go.mod": "module example.com/app/sub\n\ngo 1.27.0\n",
			},
			want: []string{`[undeclared-replacement] go.mod:10: the module "example.com/dep" is replaced with the directory "sub", which is not a vendored directory`},
		},
		{
			// The build would use other code for the packages of a component.
			name: "first-party module replaced with another directory",
			files: map[string]string{
				"go.mod":       "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/app/sub => ./other\n",
				"sub/go.mod":   "module example.com/app/sub\n\ngo 1.27.0\n",
				"other/go.mod": "module example.com/app/other\n\ngo 1.27.0\n",
			},
			want: []string{`[undeclared-replacement] go.mod:10: the first-party module "example.com/app/sub" is replaced with something other than its directory "sub"`},
		},
		{
			name: "first-party module replaced with a module",
			files: map[string]string{
				"go.mod":     "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace example.com/app/sub => example.com/fork v1.0.0\n",
				"sub/go.mod": "module example.com/app/sub\n\ngo 1.27.0\n",
			},
			want: []string{`[undeclared-replacement] go.mod:10: the first-party module "example.com/app/sub" is replaced with something other than its directory "sub"`},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			requireFindings(t, check(t, newFixture(t, tc.files)), tc.want)
		})
	}
}

func TestCheckAcceptsWhatTheModelPermits(t *testing.T) {
	t.Parallel()
	tests := map[string]map[string]string{
		"public package": {
			"architecture/model.yaml": strings.Replace(strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, api]", 1), "public: []", "public: [api]", 1),
			"api/api.go":              "// Package api is public.\npackage api\n",
		},
		"test-only package outside internal": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, suite]", 1),
			"suite/suite_test.go":     "package suite_test\n",
		},
		"command outside internal": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "packages: [app]", "packages: [app, tool]", 1),
			"tool/main.go":            "package main\n\nfunc main() {}\n",
		},
		// The nested module path does not follow its directory, so only the
		// longest module path and the longest module directory resolve the
		// imports of sub/cmd.
		"nested module": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "packages: [app]\n", "packages: [app, sub/cmd, sub/internal/lib]\n    modules: [example.com/subdep]\n", 1),
			"sub/go.mod":              "module example.com/app/tool\n\ngo 1.27.0\n\nrequire example.com/subdep v1.0.0\n",
			"sub/cmd/main.go":         "package main\n\nimport (\n\t\"example.com/app/tool/internal/lib\"\n\t\"example.com/subdep/x\"\n)\n\nfunc main() { _, _ = lib.V, x.V }\n",
			"sub/internal/lib/lib.go": "package lib\n\n// V is a value.\nconst V = 1\n",
		},
		// The module of an import is the longest required module path.
		"nested required modules": {
			"architecture/model.yaml":   strings.Replace(fixtureModel, "packages: [internal/values]\n", "packages: [internal/values]\n    modules: [example.com/dep/v2]\n", 1),
			"go.mod":                    "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/dep/v2 v2.0.0\n\texample.com/check v1.0.0\n)\n",
			"internal/values/values.go": "package values\n\nimport \"example.com/dep/v2/z\"\n\nvar _ = z.V\n",
		},
		"paths that the go command ignores": {
			"_head/head.go":           "package head\n\nimport \"example.com/forbidden\"\n",
			".hidden/hidden.go":       "package hidden\n\nimport \"example.com/forbidden\"\n",
			"internal/values/_old.go": "package values\n\nimport \"example.com/forbidden\"\n",
			"internal/values/.new.go": "package values\n\nimport \"example.com/forbidden\"\n",
			"_head/go.mod":            "module\n",
		},
		// The module of the longest module path has the shorter directory.
		"nested module with a shorter directory": {
			"architecture/model.yaml":   strings.Replace(strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, q/x]", 1), "public: []", "public: [q/x]", 1),
			"deep/er/go.mod":            "module example.com/lib\n\ngo 1.27.0\n",
			"q/go.mod":                  "module example.com/lib/sub\n\ngo 1.27.0\n",
			"q/x/x.go":                  "// Package x is public.\npackage x\n\n// V is a value.\nconst V = 1\n",
			"internal/values/values.go": "package values\n\nimport \"example.com/lib/sub/x\"\n\nvar _ = x.V\n",
		},
		"replacements with vendored source and a first-party module": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "packages: [app]", "packages: [app, sub/cmd]", 1),
			"go.mod":                  "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n)\n\nreplace (\n\texample.com/dep => ./third_party/dep\n\texample.com/app/sub => ./sub\n)\n",
			"third_party/dep/go.mod":  "module example.com/dep\n\ngo 1.27.0\n",
			"sub/go.mod":              "module example.com/app/sub\n\ngo 1.27.0\n",
			"sub/cmd/main.go":         "package main\n\nfunc main() {}\n",
		},
		"model of the largest size": {
			"architecture/model.yaml": fixtureModel + "# " + strings.Repeat("x", 1<<20-len(fixtureModel)-3) + "\n",
		},
		// Only production uses form a cycle: the test files of store use
		// testkit, which uses store.
		"loop through a test use": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "    packages: [internal/testkit]\n", "    packages: [internal/testkit]\n    uses: [store]\n", 1),
		},
		// A first-party module that a module requires stays first party, so
		// the component rules apply to its packages, not the module rules.
		"required first-party module": {
			"architecture/model.yaml":   strings.Replace(strings.Replace(fixtureModel, "packages: [internal/values]", "packages: [internal/values, sub/lib]", 1), "public: []", "public: [sub/lib]", 1),
			"go.mod":                    "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n\texample.com/app/sub v0.0.0\n)\n\nreplace example.com/app/sub => ./sub\n",
			"sub/go.mod":                "module example.com/app/sub\n\ngo 1.27.0\n",
			"sub/lib/lib.go":            "// Package lib is public.\npackage lib\n\n// V is a value.\nconst V = 1\n",
			"internal/values/values.go": "package values\n\nimport \"example.com/app/sub/lib\"\n\n// X is a value.\nconst X = lib.V\n",
		},
		// The longest module path owns an import, so a required module below
		// the first-party module path is not first party.
		"required module below the first-party path": {
			"architecture/model.yaml": strings.Replace(fixtureModel, "    modules: [example.com/dep]\n", "    modules: [example.com/dep, example.com/app/dep]\n", 1),
			"go.mod":                  "module example.com/app\n\ngo 1.27.0\n\nrequire (\n\texample.com/dep v1.0.0\n\texample.com/check v1.0.0\n\texample.com/app/dep v1.0.0\n)\n",
			"internal/store/extra.go": "package store\n\nimport \"example.com/app/dep/sub\"\n\nvar _ = sub.Z\n",
		},
		"cgo and standard library": {
			"internal/values/values.go": "package values\n\nimport (\n\t\"C\"\n\t\"net/http\"\n)\n\nvar _ = http.MethodGet\n",
		},
	}
	for name, files := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if got := check(t, newFixture(t, files)); len(got) != 0 {
				t.Errorf("Check() findings = %q, want none", got)
			}
		})
	}
}

// TestCheckReadsTheWorkingTree deletes tracked files without a commit. The
// check reads the working tree, so the package of the files is stale.
func TestCheckReadsTheWorkingTree(t *testing.T) {
	t.Parallel()
	r := newFixture(t, nil)
	for _, name := range []string{"internal/testkit/testkit.go", "internal/store/store_test.go"} {
		if err := os.Remove(filepath.Join(r.Dir, filepath.FromSlash(name))); err != nil {
			t.Fatal(err)
		}
	}

	requireFindings(t, check(t, r), []string{`[stale-package] architecture/model.yaml:27: the package "internal/testkit" of "testkit" has no Go file`})
}

func TestCheckValidatesTheModel(t *testing.T) {
	t.Parallel()
	edit := func(old, replacement string) map[string]string {
		return map[string]string{"architecture/model.yaml": strings.Replace(fixtureModel, old, replacement, 1)}
	}
	tests := []struct {
		name  string
		files map[string]string
		want  []string
	}{
		{"bad layer name", edit("- name: core\n    description: Values", "- name: Core\n    description: Values"),
			[]string{`[invalid-model] architecture/model.yaml:6: the layer name "Core"`, `[invalid-model] architecture/model.yaml:3: the layer "entry" may use the unknown layer "core"`,
				`[invalid-model] architecture/model.yaml:6: the layer "Core" may use the unknown layer "core"`,
				`[invalid-model] architecture/model.yaml:15: the component "values" has the unknown layer "core"`,
				`[invalid-model] architecture/model.yaml:19: the component "store" has the unknown layer "core"`,
				`[invalid-model] architecture/model.yaml:27: the component "testkit" has the unknown layer "core"`}},
		{"duplicate layer", edit("  - name: core\n    description: Values and stores.\n    may_use: [core]\n", "  - name: core\n    description: Values and stores.\n    may_use: [core]\n  - name: core\n    description: Again.\n    may_use: [core]\n"),
			[]string{`[invalid-model] architecture/model.yaml:9: the layer "core" is defined twice`}},
		{"bad component name", edit("- name: testkit", "- name: Test_kit"),
			[]string{`[invalid-model] architecture/model.yaml:19: the component "store" uses the unknown component "testkit"`,
				`[invalid-model] architecture/model.yaml:27: the component name "Test_kit"`,
				`[forbidden-import] internal/store/store_test.go:6: the import "example.com/app/internal/testkit" is in "Test_kit", which "store" does not use`}},
		{"duplicate component", edit("- name: testkit", "- name: values"),
			[]string{`[invalid-model] architecture/model.yaml:15: the component "values" is defined twice`,
				`[invalid-model] architecture/model.yaml:19: the component "store" uses the unknown component "testkit"`,
				`[invalid-model] architecture/model.yaml:27: the component "values" is defined twice`}},
		{"empty responsibility", edit("responsibility: Holds values.", "responsibility: \" \""),
			[]string{`[invalid-model] architecture/model.yaml:15: the component "values" has no responsibility`}},
		{"no package", edit("packages: [internal/values]", "packages: []"),
			[]string{`[invalid-model] architecture/model.yaml:15: the component "values" has no package`, `[unassigned-package] internal/values`}},
		{"bad package path", edit("packages: [internal/testkit]", "packages: [internal/testkit, ../out, /abs, a\\\\b, ./x]"),
			[]string{`[invalid-model] architecture/model.yaml:27: the package "../out"`, `[invalid-model] architecture/model.yaml:27: the package "/abs"`,
				`[invalid-model] architecture/model.yaml:27: the package "a\\\\b"`, `[invalid-model] architecture/model.yaml:27: the package "./x"`,
				`[stale-package]`, `[stale-package]`, `[stale-package]`, `[stale-package]`}},
		{"package in two components", edit("packages: [internal/testkit]", "packages: [internal/testkit, internal/values]"),
			[]string{`[invalid-model] architecture/model.yaml:27: the package "internal/values" is in "values" and in "testkit"`}},
		{"self use", edit("uses: [values]\n", "uses: [values, store]\n"),
			[]string{`[invalid-model] architecture/model.yaml:19: the component "store" uses itself`}},
		{"use against the layers", edit("    packages: [internal/values]\n", "    packages: [internal/values]\n    uses: [app]\n"),
			[]string{`[invalid-model] architecture/model.yaml:15: the layer "core" of "values" may not use the layer "entry" of "app"`,
				`[invalid-model] architecture/model.yaml:15: the uses of "values" close the cycle "app" -> "values" -> "app"`}},
		{"cycle in one layer", edit("    packages: [internal/values]\n", "    packages: [internal/values]\n    uses: [store]\n"),
			[]string{`[invalid-model] architecture/model.yaml:20: the uses of "store" close the cycle "values" -> "store" -> "values"`}},
		{"use listed twice", edit("test_uses: [testkit]", "test_uses: [testkit, values]"),
			[]string{`[invalid-model] architecture/model.yaml:19: the uses of "store" list "values" twice`}},
		{"invalid module", edit("modules: [example.com/dep]", "modules: [example.com/dep, Not A Module]"),
			[]string{`[invalid-model] architecture/model.yaml:19: the module "Not A Module" of "store" is not a valid module path`}},
		{"module listed twice", edit("test_modules: [example.com/check]", "test_modules: [example.com/check, example.com/dep]"),
			[]string{`[invalid-model] architecture/model.yaml:19: the modules of "store" list "example.com/dep" twice`}},
		{"public package in no component", edit("public: []", "public: [nowhere, nowhere]"),
			[]string{`[invalid-model] architecture/model.yaml:31: the public package "nowhere" is in no component`, `[invalid-model] architecture/model.yaml:31: the public package "nowhere" is in no component`,
				`[invalid-model] architecture/model.yaml:31: the public packages list "nowhere" twice`}},
		{"public package under internal", edit("public: []", "public: [internal/values]"),
			[]string{`[invalid-model] architecture/model.yaml:31: the public package "internal/values" is under internal/`}},
		{"bad vendored directory", edit("vendored: [third_party]", "vendored: [third_party, ., third_party]"),
			[]string{`[invalid-model] architecture/model.yaml:32: the vendored directory "."`,
				`[invalid-model] architecture/model.yaml:10: the package "app" of "app" is in the vendored directory "."`,
				`[invalid-model] architecture/model.yaml:15: the package "internal/values" of "values" is in the vendored directory "."`,
				`[invalid-model] architecture/model.yaml:19: the package "internal/store" of "store" is in the vendored directory "."`,
				`[invalid-model] architecture/model.yaml:27: the package "internal/testkit" of "testkit" is in the vendored directory "."`,
				`[invalid-model] architecture/model.yaml:32: the vendored directories list "third_party" twice`,
				`[stale-package]`, `[stale-package]`, `[stale-package]`, `[stale-package]`}},
		{"package in a vendored directory", edit("vendored: [third_party]", "vendored: [third_party, internal/testkit]"),
			[]string{`[invalid-model] architecture/model.yaml:27: the package "internal/testkit" of "testkit" is in the vendored directory "internal/testkit"`,
				`[stale-package] architecture/model.yaml:27`,
				`[unresolved-import] internal/store/store_test.go:6: the import "example.com/app/internal/testkit" names a first-party package that has no Go file`}},
		{"missing fix-it", edit("  stale-diagram: Fix stale-diagram.\n", ""),
			[]string{`[invalid-model] architecture/model.yaml:33: the rule "stale-diagram" has no fix-it message`}},
		{"unknown rule", edit("  stale-diagram: Fix stale-diagram.\n", "  stale-diagram: Fix stale-diagram.\n  made-up: Fix it.\n"),
			[]string{`[invalid-model] architecture/model.yaml:33: the rule "made-up" is unknown`}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			requireFindings(t, check(t, newFixture(t, tc.files)), tc.want)
		})
	}
}

func TestCheckReportsAModelWithoutRules(t *testing.T) {
	t.Parallel()
	model, _, _ := strings.Cut(fixtureModel, "rules:\n")

	got := check(t, newFixture(t, map[string]string{"architecture/model.yaml": model}))

	want := "[invalid-model] architecture/model.yaml: the rule \"unassigned-package\" has no fix-it message\n" +
		"    fix: The model gives no fix-it message for this rule."
	if len(got) != 15 || got[0] != want {
		t.Errorf("Check() findings = %q, want 15 findings that start with %q", got, want)
	}
}

func TestCheckRejectsInputThatItCannotDecode(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		want  string
	}{
		{"no model", map[string]string{"architecture/model.yaml": ""}, "the working tree has no architecture/model.yaml"},
		{"empty model", map[string]string{"architecture/model.yaml": "\n"}, "architecture/model.yaml: decode the YAML document"},
		{"unknown field", map[string]string{"architecture/model.yaml": fixtureModel + "extra: 1\n"}, "field extra not found"},
		{"duplicate key", map[string]string{"architecture/model.yaml": "version: 1\nversion: 1\n"}, "already defined"},
		{"two documents", map[string]string{"architecture/model.yaml": fixtureModel + "---\nversion: 1\n"}, "more than one YAML document"},
		{"alias", map[string]string{"architecture/model.yaml": "version: 1\npublic: &p [a]\nvendored: *p\n"}, "aliases and anchors are not supported"},
		{"custom tag", map[string]string{"architecture/model.yaml": "version: !!binary MQ==\n"}, `the YAML tag "!!binary" is not supported`},
		{"wrong version", map[string]string{"architecture/model.yaml": strings.Replace(fixtureModel, "version: 1", "version: 2", 1)}, "the model version must be 1"},
		{"too large", map[string]string{"architecture/model.yaml": fixtureModel + "# " + strings.Repeat("x", 1<<20) + "\n"}, "larger than 1048576 bytes"},
		{"unparsable Go file", map[string]string{"internal/values/values.go": "package values\n\nimport \"secret-canary\nfunc"}, "internal/values/values.go: cannot parse the Go file"},
		{"unparsable go.mod", map[string]string{"go.mod": "module\n"}, "go.mod: cannot parse the module file"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := architecture.Check(t.Context(), newFixture(t, tc.files).Dir)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("Check() error = %v, want an error that contains %q", err, tc.want)
			}
			if strings.Contains(err.Error(), "secret-canary") {
				t.Errorf("Check() error = %q, want no source text", err)
			}
		})
	}
}

func TestCheckReportsAMissingRepository(t *testing.T) {
	t.Parallel()
	if _, err := architecture.Check(t.Context(), t.TempDir()); err == nil {
		t.Fatal("Check(directory outside Git) returned no error")
	}
}

func TestFindingOutputIsSafe(t *testing.T) {
	t.Parallel()
	f := architecture.Finding{
		Rule:     architecture.RuleForbiddenImport,
		Location: "a.go:1\n::error::x",
		Message:  "the import \"x\r\ny\" is bad",
		FixIt:    "do\tthis",
	}

	got := f.String()

	want := "[forbidden-import] a.go:1\\n::error::x: the import \\\"x\\r\\ny\\\" is bad\n    fix: do\\tthis"
	if got != want {
		t.Errorf("Finding.String() = %q, want %q", got, want)
	}
	for line := range strings.SplitSeq(got, "\n") {
		if strings.HasPrefix(line, "::") {
			t.Errorf("Finding.String() has the line %q, which starts a workflow command", line)
		}
	}
	if long := architecture.Clean(strings.Repeat("a", 3000)); len(long) != 2003 || !strings.HasSuffix(long, "...") {
		t.Errorf("Clean(3000 bytes) has %d bytes, want 2000 and an ellipsis", len(long))
	}
	for in, want := range map[string]string{
		strings.Repeat("a", 2000): strings.Repeat("a", 2000),
		"a\u202eb":                `a\u202eb`,
		"a\xffb":                  `a\xffb`,
		"café":                    "café",
	} {
		if got := architecture.Clean(in); got != want {
			t.Errorf("Clean(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestWriteShowsAtMost500Findings(t *testing.T) {
	t.Parallel()
	findings := make([]architecture.Finding, 502)
	for i := range findings {
		findings[i] = architecture.Finding{Rule: "r", Location: "l", Message: "m", FixIt: "f"}
	}
	var out strings.Builder

	if err := architecture.Write(&out, findings); err != nil {
		t.Fatal(err)
	}

	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	if len(lines) != 1001 || lines[1000] != "archcheck: 2 more findings are not shown" {
		t.Errorf("Write(502 findings) printed %d lines ending %q, want 1001 lines and the count of the others", len(lines), lines[len(lines)-1])
	}
	if err := architecture.Write(failingWriter{}, findings[:1]); err == nil {
		t.Error("Write(failing writer) returned no error")
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("closed") }

// commitModel replaces the model of r and commits it.
func commitModel(r *gittest.Repo, model string) string {
	return r.Commit(map[string]string{"architecture/model.yaml": model})
}
