package conformance_test

import (
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/rogpeppe/go-internal/testscript"
)

// fakeBinary prints a doctor envelope and exits with the status that its
// first argument names.
const fakeBinary = "#!/bin/sh\n" +
	"ok=false\nif [ \"$1\" = 0 ]; then ok=true; fi\n" +
	"printf '{\"command\":\"doctor\",\"schema_version\":1,\"ok\":%s}\\n' \"$ok\"\nexit \"$1\"\n"

// TestHarnessCommandsFail runs scripts with false assertions against a fake
// binary. Each script must fail, and the script true-asserts must pass: a
// command that cannot fail would make each case pass.
func TestHarnessCommandsFail(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	bin := filepath.Join(dir, "lilrae")
	if err := os.WriteFile(bin, []byte(fakeBinary), 0o700); err != nil { //nolint:gosec // G306: the fake binary needs the owner execute bit; 0700 gives no access to other users.
		t.Fatal(err)
	}
	scripts := map[string]string{
		"true-asserts":  "lilrae 0\nstatus 0\njq stdout 'envelope(\"doctor\"; $status)'\n! lilrae 1\nstatus 1\njq stdout 'envelope(\"doctor\"; $status)'\n",
		"false":         "lilrae 0\njq stdout 'false'\n",
		"many-values":   "lilrae 0\njq stdout 'true, true'\n",
		"no-value":      "lilrae 0\njq stdout 'empty'\n",
		"query-error":   "lilrae 0\njq stdout '.command | keys'\n",
		"not-boolean":   "lilrae 0\njq stdout '1'\n",
		"no-run":        "jq data.json '$status == 0'\n-- data.json --\n{}\n",
		"other-command": "lilrae 0\njq stdout 'envelope(\"lab start\"; $status)'\n",
		"ok-and-status": "! lilrae 1\njq stdout 'envelope(\"doctor\"; 0)'\n",
		"duplicate":     "jq data.json 'true'\n-- data.json --\n{\"a\":1,\"a\":2}\n",
		"two-values":    "jq data.json 'true'\n-- data.json --\n{} {}\n",
		"status":        "lilrae 0\nstatus 3\n",
		"exit-status":   "lilrae 1\n",
		"schema":        "lilrae 0\nschema doctor-result.schema.json stdout\n",
	}
	scriptDir := filepath.Join(dir, "scripts")
	if err := os.Mkdir(scriptDir, 0o750); err != nil {
		t.Fatal(err)
	}
	for name, script := range scripts {
		if err := os.WriteFile(filepath.Join(scriptDir, name+".txtar"), []byte(script), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	r := &recorder{}

	testscript.RunT(r, params(t, bin, scriptDir, nil))

	var want []string
	for name := range scripts {
		if name != "true-asserts" {
			want = append(want, name)
		}
	}
	slices.Sort(want)
	slices.Sort(r.failed)
	if len(r.ran) != len(scripts) || !slices.Equal(want, r.failed) {
		t.Errorf("of %d scripts, %d ran and %q failed; want each to run and %q to fail", len(scripts), len(r.ran), r.failed, want)
	}
}

// recorder is a [testscript.T] that records the scripts that fail.
type recorder struct {
	// name is the script of a child recorder.
	name string
	// ran and failed list the scripts that ran and that failed, in the root
	// recorder.
	ran, failed []string
	root        *recorder
}

// stopScript ends a script after a failure.
type stopScript struct{}

func (r *recorder) Run(name string, f func(testscript.T)) {
	root := r
	if r.root != nil {
		root = r.root
	}
	root.ran = append(root.ran, name)
	defer func() {
		if p := recover(); p != nil && p != (stopScript{}) {
			panic(p)
		}
	}()
	f(&recorder{name: name, root: root})
}

func (r *recorder) Fatal(...any) { r.FailNow() }

func (r *recorder) FailNow() {
	if r.root == nil {
		panic("the harness failed outside a script")
	}
	r.root.failed = append(r.root.failed, r.name)
	panic(stopScript{})
}

func (*recorder) Skip(...any)   {}
func (*recorder) Parallel()     {}
func (*recorder) Log(...any)    {}
func (*recorder) Verbose() bool { return false }
