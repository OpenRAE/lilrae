package mutation

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"
)

// Gremlins parses each exclusion as CSV before it compiles the expressions.
// A comma in a literal path must not split a rule or exclude another file.
func TestExclusionsKeepLiteralCommas(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"sub,calc/go.mod", "_scratch,calc/f.go", "calc/never,more.go"} {
		file := filepath.Join(dir, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(file), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(file, []byte("//go:build never\n\npackage calc\n"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	rules, err := exclusions(dir)
	if err != nil {
		t.Fatal(err)
	}
	var patterns []*regexp.Regexp
	for _, rule := range rules {
		fields, err := csv.NewReader(strings.NewReader(rule)).Read()
		if err != nil {
			t.Fatal(err)
		}
		for _, field := range fields {
			patterns = append(patterns, regexp.MustCompile(field))
		}
	}
	for name, want := range map[string]bool{
		"sub,calc/f.go": true, "_scratch,calc/f.go": true, "calc/never,more.go": true,
		"sub/f.go": false, "calc/more.go": false, "_scratchpad/f.go": false,
	} {
		got := slices.ContainsFunc(patterns, func(pattern *regexp.Regexp) bool { return pattern.MatchString(name) })
		if got != want {
			t.Errorf("exclusions of %q match %q = %t, want %t", rules, name, got, want)
		}
	}
}
