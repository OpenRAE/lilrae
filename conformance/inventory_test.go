package conformance_test

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// inventoryPath is the contract inventory, relative to this package.
const inventoryPath = "../docs/reference/conformance-inventory.md"

// caseRef matches a case named in the inventory.
var caseRef = regexp.MustCompile("`((?:cases|lab)/[a-z0-9-]+\\.txtar)`")

// TestInventory checks the contract inventory: each contract row names a case
// or the later port that owns it, each named case exists, and each case is
// named.
func TestInventory(t *testing.T) {
	t.Parallel()
	data, err := os.ReadFile(filepath.FromSlash(inventoryPath))
	if err != nil {
		t.Fatal(err)
	}
	named := namedCases(t, string(data))
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

// namedCases returns the cases that the contract rows of the inventory name.
// It reports each contract row that names no case and no later port.
func namedCases(t *testing.T, inventory string) map[string]bool {
	t.Helper()
	named := map[string]bool{}
	for line := range strings.SplitSeq(inventory, "\n") {
		cells := strings.Split(line, "|")
		if len(cells) != 7 || strings.TrimSpace(cells[4]) != "contract" {
			continue
		}
		refs := caseRef.FindAllStringSubmatch(cells[5], -1)
		if len(refs) == 0 && !strings.Contains(cells[5], "Go port") {
			t.Errorf("the contract %s names no case and no later port", strings.TrimSpace(cells[1]))
		}
		for _, ref := range refs {
			named[ref[1]] = true
		}
	}
	return named
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
