package conformance_test

import (
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"

	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/extension"
	east "github.com/yuin/goldmark/extension/ast"
	"github.com/yuin/goldmark/text"
)

// inventoryPath is the contract inventory, relative to this package.
const inventoryPath = "../docs/reference/conformance-inventory.md"

// caseRef matches a case that a code span of the inventory names.
var caseRef = regexp.MustCompile(`^(?:cases|lab)/[a-z0-9-]+\.txtar$`)

// TestInventory checks the contract inventory: each contract row names a case
// or the later port that owns it, each named case exists, and each case is
// named.
func TestInventory(t *testing.T) {
	t.Parallel()
	source, err := os.ReadFile(filepath.FromSlash(inventoryPath))
	if err != nil {
		t.Fatal(err)
	}
	named := map[string]bool{}
	for _, row := range inventoryRows(t, source) {
		if row.class != "contract" {
			continue
		}
		if len(row.cases) == 0 && !strings.Contains(row.coverage, "Go port") {
			t.Errorf("the contract %s names no case and no later port", row.id)
		}
		for _, ref := range row.cases {
			named[ref] = true
		}
	}
	checkNamedCases(t, named)
}

// checkNamedCases checks that each named case exists, that a lab case is
// named, and that each case in testdata is named.
func checkNamedCases(t *testing.T, named map[string]bool) {
	t.Helper()
	lab := false
	for ref := range named {
		if _, err := os.Stat(filepath.Join("testdata", filepath.FromSlash(ref))); err != nil {
			t.Errorf("the inventory names the missing case %s", ref)
		}
		lab = lab || strings.HasPrefix(ref, "lab/")
	}
	if !lab {
		t.Error("the inventory names no lab case")
	}
	for _, ref := range caseFiles(t) {
		if !named[ref] {
			t.Errorf("no inventory row names the case %s", ref)
		}
	}
}

// inventoryRow is a row of an inventory table.
type inventoryRow struct {
	id, class, coverage string
	// cases are the cases that the code spans of the coverage cell name.
	cases []string
}

// inventoryRows returns the rows of each table of the inventory that has the
// columns ID, Class, and Coverage. goldmark parses the Markdown with its
// table extension, which follows GitHub Flavored Markdown.
func inventoryRows(t *testing.T, source []byte) []inventoryRow {
	t.Helper()
	doc := goldmark.New(goldmark.WithExtensions(extension.Table)).Parser().Parse(text.NewReader(source))
	var rows []inventoryRow
	for n := doc.FirstChild(); n != nil; n = n.NextSibling() {
		if table, ok := n.(*east.Table); ok {
			rows = append(rows, tableRows(t, table, source)...)
		}
	}
	if len(rows) == 0 {
		t.Fatal("the inventory has no table with the columns ID, Class, and Coverage")
	}
	return rows
}

// tableRows returns the rows of a table with the columns ID, Class, and
// Coverage, or nothing for another table.
func tableRows(t *testing.T, table *east.Table, source []byte) []inventoryRow {
	t.Helper()
	header, ok := table.FirstChild().(*east.TableHeader)
	if !ok {
		return nil
	}
	var columns []string
	for _, cell := range children(header) {
		columns = append(columns, cellText(cell, source))
	}
	id, class, coverage := slices.Index(columns, "ID"), slices.Index(columns, "Class"), slices.Index(columns, "Coverage")
	if id < 0 || class < 0 || coverage < 0 {
		return nil
	}
	var rows []inventoryRow
	for row := header.NextSibling(); row != nil; row = row.NextSibling() {
		cells := children(row)
		if len(cells) != len(columns) {
			t.Fatalf("an inventory row has %d cells, not %d", len(cells), len(columns))
		}
		rows = append(rows, inventoryRow{
			id:       cellText(cells[id], source),
			class:    cellText(cells[class], source),
			coverage: cellText(cells[coverage], source),
			cases:    caseRefs(cells[coverage], source),
		})
	}
	return rows
}

// children returns the child nodes of n.
func children(n ast.Node) []ast.Node {
	var nodes []ast.Node
	for child := n.FirstChild(); child != nil; child = child.NextSibling() {
		nodes = append(nodes, child)
	}
	return nodes
}

// cellText returns the text of a table cell without its Markdown markup.
func cellText(cell ast.Node, source []byte) string {
	var b strings.Builder
	walkText(cell, source, func(segment []byte) { b.Write(segment) })
	return strings.TrimSpace(b.String())
}

// caseRefs returns the cases that the code spans of a table cell name.
func caseRefs(cell ast.Node, source []byte) []string {
	var refs []string
	for _, n := range children(cell) {
		if _, ok := n.(*ast.CodeSpan); !ok {
			continue
		}
		if ref := cellText(n, source); caseRef.MatchString(ref) {
			refs = append(refs, ref)
		}
	}
	return refs
}

// walkText calls f with each text segment below n, in order.
func walkText(n ast.Node, source []byte, f func([]byte)) {
	for _, child := range children(n) {
		if t, ok := child.(*ast.Text); ok {
			f(t.Segment.Value(source))
			continue
		}
		walkText(child, source, f)
	}
}

// caseFiles returns the cases in testdata, as the inventory names them.
func caseFiles(t *testing.T) []string {
	t.Helper()
	var refs []string
	for _, dir := range []string{"cases", "lab"} {
		files, err := filepath.Glob(filepath.Join("testdata", dir, "*.txtar"))
		if err != nil {
			t.Fatal(err)
		}
		for _, file := range files {
			refs = append(refs, dir+"/"+filepath.Base(file))
		}
	}
	return refs
}
