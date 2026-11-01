package conformance_test

import (
	"bytes"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// TestSchemasRequireTheirVersion checks that each published schema with a
// top-level schema_version property requires it. A reader rejects a document
// without its version, so the schema must reject it too.
func TestSchemasRequireTheirVersion(t *testing.T) {
	t.Parallel()
	fsys := os.DirFS(filepath.FromSlash(schemaDir))
	names, err := fs.Glob(fsys, "*.schema.json")
	if err != nil {
		t.Fatal(err)
	}
	versioned := 0
	for _, name := range names {
		object := schemaObject(t, fsys, name)
		properties, ok := object["properties"].(map[string]any)
		if !ok {
			continue
		}
		if _, found := properties["schema_version"]; !found {
			continue
		}
		versioned++
		required, ok := object["required"].([]any)
		if !ok || !slices.Contains(required, any("schema_version")) {
			t.Errorf("the schema %s has a schema_version property that it does not require", name)
		}
	}
	if versioned == 0 {
		t.Error("no published schema has a schema_version property")
	}
}

// schemaObject returns the published schema name of fsys as a JSON object.
func schemaObject(t *testing.T, fsys fs.FS, name string) map[string]any {
	t.Helper()
	data, err := fs.ReadFile(fsys, name)
	if err != nil {
		t.Fatal(err)
	}
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("decode the schema %s: %v", name, err)
	}
	object, ok := doc.(map[string]any)
	if !ok {
		t.Fatalf("the schema %s is not a JSON object", name)
	}
	return object
}
