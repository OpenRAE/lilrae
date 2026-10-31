package architecture_test

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
)

const (
	diagramBegin = "<!-- Generated from architecture/model.yaml by archcheck diagram. Do not edit. -->"
	diagramEnd   = "<!-- End of the generated diagram. -->"
)

// diagramModel returns the fixture model with a hyphenated component name and
// a layer without components.
func diagramModel() string {
	return strings.Replace(strings.ReplaceAll(fixtureModel, "testkit", "test-kit"),
		"    may_use: [core]\n", "    may_use: [core]\n  - name: spare\n    description: Has no component.\n    may_use: [spare]\n", 1)
}

// fixtureDiagram is the diagram of diagramModel.
const fixtureDiagram = "```mermaid\n" +
	"flowchart TB\n" +
	"    subgraph layer_entry[entry]\n" +
	"        component_app[app]\n" +
	"    end\n" +
	"    subgraph layer_core[core]\n" +
	"        component_values[values]\n" +
	"        component_store[store]\n" +
	"        component_test_kit[test-kit]\n" +
	"    end\n" +
	"    component_app --> component_values\n" +
	"    component_app --> component_store\n" +
	"    component_store --> component_values\n" +
	"    component_store -. test .-> component_test_kit\n" +
	"```"

// diagramDoc returns a document whose generated block holds block.
func diagramDoc(block string) string {
	return "# Architecture\n\n" + diagramBegin + block + diagramEnd + "\n\nThe end.\n"
}

func TestDiagramReportsAStaleBlock(t *testing.T) {
	t.Parallel()
	doc := diagramDoc("\nold\n")
	r := newFixture(t, map[string]string{"architecture/model.yaml": diagramModel(), "docs/arch.md": doc})

	report, err := architecture.Diagram(t.Context(), r.Dir, "docs/arch.md", false)
	if err != nil {
		t.Fatalf("Diagram() returned error %v", err)
	}

	requireFindings(t, findingStrings(report), []string{"[stale-diagram] docs/arch.md: the generated diagram differs from the model\n    fix: Fix stale-diagram."})
	if got := readFile(t, r.Dir, "docs/arch.md"); got != doc {
		t.Errorf("Diagram() without write changed the document to %q", got)
	}
}

func TestDiagramWritesTheBlock(t *testing.T) {
	t.Parallel()
	r := newFixture(t, map[string]string{"architecture/model.yaml": diagramModel(), "docs/arch.md": diagramDoc("\nold\n")})
	doc := filepath.Join(r.Dir, "docs", "arch.md")

	report, err := architecture.Diagram(t.Context(), r.Dir, doc, true)
	if err != nil || len(report.Findings) != 0 {
		t.Fatalf("Diagram(write) = %q, %v, want no findings and no error", findingStrings(report), err)
	}

	if got, want := readFile(t, r.Dir, "docs/arch.md"), diagramDoc("\n"+fixtureDiagram+"\n"); got != want {
		t.Errorf("Diagram(write) wrote\n%s\nwant\n%s", got, want)
	}
	if report, err := architecture.Diagram(t.Context(), r.Dir, "docs/arch.md", false); err != nil || len(report.Findings) != 0 {
		t.Errorf("Diagram() after the write = %q, %v, want no findings and no error", findingStrings(report), err)
	}
}

func TestDiagramReportsAnInvalidModel(t *testing.T) {
	t.Parallel()
	r := newFixture(t, map[string]string{
		"architecture/model.yaml": strings.Replace(fixtureModel, "may_use: [entry, core]", "may_use: [entry, core, nowhere]", 1),
		"docs/arch.md":            diagramDoc("\nold\n"),
	})

	report, err := architecture.Diagram(t.Context(), r.Dir, "docs/arch.md", true)
	if err != nil {
		t.Fatalf("Diagram() returned error %v", err)
	}

	requireFindings(t, findingStrings(report), []string{`[invalid-model] architecture/model.yaml:3: the layer "entry" may use the unknown layer "nowhere"`})
}

func TestDiagramRejectsAnUnusableDocument(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		doc   string
		want  string
	}{
		{name: "no begin marker", files: map[string]string{"docs/arch.md": "# Architecture\n"}, doc: "docs/arch.md", want: "docs/arch.md has no generated diagram block"},
		{name: "no end marker", files: map[string]string{"docs/arch.md": diagramBegin + "\n"}, doc: "docs/arch.md", want: "docs/arch.md has no end marker for the generated diagram"},
		{name: "missing document", doc: "docs/none.md", want: "read docs/none.md"},
		{name: "outside the working tree", doc: "../arch.md", want: "is not in the working tree"},
		{name: "no model", files: map[string]string{"architecture/model.yaml": ""}, doc: "docs/arch.md", want: "the working tree has no architecture/model.yaml"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := newFixture(t, tc.files)

			_, err := architecture.Diagram(t.Context(), r.Dir, tc.doc, false)

			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Errorf("Diagram() error = %v, want an error that contains %q", err, tc.want)
			}
		})
	}
}

// readFile returns the content of the file name in dir.
func readFile(t *testing.T, dir, name string) string {
	t.Helper()
	data, err := fs.ReadFile(os.DirFS(dir), name)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}
