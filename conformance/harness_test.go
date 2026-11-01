package conformance_test

import (
	"bytes"
	"encoding/json/jsontext"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/itchyny/gojq"
	"github.com/rogpeppe/go-internal/testscript"
	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/santhosh-tekuri/jsonschema/v6/kind"
)

const (
	// binaryVar names the binary under test by an absolute path.
	binaryVar = "LILRAE_CONFORMANCE_BINARY"
	// schemaDir holds the published schemas, relative to this package.
	schemaDir = "../docs/reference/schemas"
	// schemaBase is the start of the $id of each published schema.
	schemaBase = "https://openrae.github.io/lilrae/reference/schemas/"
	// lastRunKey keys the outcome of the last lilrae command of a script.
	lastRunKey = "lilrae-last-run"
	// jqModule is the jq module of the case definitions, in testdata.
	jqModule = "conformance"
)

// lastRun is the outcome of the last lilrae command of a script.
type lastRun struct {
	ran    bool
	status int
}

func TestConformance(t *testing.T) {
	t.Parallel()
	runCases(t, filepath.Join("testdata", "cases"), nil)
}

// runCases runs each script in dir against the binary under test. env adds
// variables to the environment of each script.
func runCases(t *testing.T, dir string, env map[string]string) {
	t.Helper()
	testscript.Run(t, params(t, binary(t), dir, env))
}

// params returns the parameters of the scripts in dir, which run the binary
// bin. env adds variables to the environment of each script.
func params(t *testing.T, bin, dir string, env map[string]string) testscript.Params {
	t.Helper()
	schemas := loadSchemas(t)
	modules, err := filepath.Abs("testdata")
	if err != nil {
		t.Fatal(err)
	}
	return testscript.Params{
		Dir:                dir,
		RequireUniqueNames: true,
		Setup: func(e *testscript.Env) error {
			e.Values[lastRunKey] = &lastRun{}
			for name, value := range env {
				e.Setenv(name, value)
			}
			return isolate(e)
		},
		Cmds: map[string]func(*testscript.TestScript, bool, []string){
			"lilrae":  runBinary(bin),
			"cleanup": deferBinary(bin),
			"status":  checkStatus,
			"schema":  checkSchema(schemas),
			"jq":      checkQuery(modules),
		},
	}
}

// binary returns the binary under test, or stops the test when
// LILRAE_CONFORMANCE_BINARY does not name an executable file by an absolute
// path.
func binary(t *testing.T) string {
	t.Helper()
	bin := os.Getenv(binaryVar)
	if !filepath.IsAbs(bin) {
		t.Fatalf("%s must name the binary under test by an absolute path; it is %q", binaryVar, bin)
	}
	if _, err := exec.LookPath(bin); err != nil {
		t.Fatalf("%s=%q names no executable file", binaryVar, bin)
	}
	return bin
}

// isolate gives the script its own home, XDG, and Docker configuration
// directories below its work directory.
func isolate(e *testscript.Env) error {
	home := filepath.Join(e.WorkDir, ".home")
	dirs := map[string]string{
		"HOME":            home,
		"XDG_CONFIG_HOME": filepath.Join(home, ".config"),
		"XDG_CACHE_HOME":  filepath.Join(home, ".cache"),
		"XDG_DATA_HOME":   filepath.Join(home, ".local", "share"),
		"DOCKER_CONFIG":   filepath.Join(home, ".docker"),
	}
	for name, dir := range dirs {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return fmt.Errorf("create %s: %w", name, err)
		}
		e.Setenv(name, dir)
	}
	e.Setenv("NO_COLOR", "1")
	return nil
}

// loadSchemas compiles each published schema from a closed registry: a
// reference resolves only to another published schema.
func loadSchemas(t *testing.T) map[string]*jsonschema.Schema {
	t.Helper()
	fsys := os.DirFS(filepath.FromSlash(schemaDir))
	entries, err := fs.ReadDir(fsys, ".")
	if err != nil {
		t.Fatalf("read the schemas: %v", err)
	}
	c := jsonschema.NewCompiler()
	c.DefaultDraft(jsonschema.Draft2020)
	c.UseLoader(jsonschema.SchemeURLLoader{})
	var names []string
	for _, entry := range entries {
		if name := entry.Name(); strings.HasSuffix(name, ".schema.json") {
			addSchema(t, c, fsys, name)
			names = append(names, name)
		}
	}
	schemas := map[string]*jsonschema.Schema{}
	for _, name := range names {
		schema, err := c.Compile(schemaBase + name)
		if err != nil {
			t.Fatalf("compile the schema %s: %v", name, err)
		}
		schemas[name] = schema
	}
	return schemas
}

// addSchema adds the schema file name of fsys to the registry of c. Its $id
// must be the published location of the file.
func addSchema(t *testing.T, c *jsonschema.Compiler, fsys fs.FS, name string) {
	t.Helper()
	data, err := fs.ReadFile(fsys, name)
	if err != nil {
		t.Fatalf("read the schema %s: %v", name, err)
	}
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("decode the schema %s: %v", name, err)
	}
	if object, ok := doc.(map[string]any); !ok || object["$id"] != schemaBase+name {
		t.Fatalf("the schema %s must have the $id %q", name, schemaBase+name)
	}
	if err := c.AddResource(schemaBase+name, doc); err != nil {
		t.Fatalf("add the schema %s: %v", name, err)
	}
}

// runBinary returns the lilrae command: it runs the binary under test with
// the arguments and records the exit status. Without a negation the command
// must exit with status 0; with one it must not.
func runBinary(bin string) func(*testscript.TestScript, bool, []string) {
	return func(ts *testscript.TestScript, neg bool, args []string) {
		last := lastRunOf(ts)
		err := ts.Exec(bin, args...)
		last.ran, last.status = true, 0
		if err != nil {
			var exitErr *exec.ExitError
			if !errors.As(err, &exitErr) || exitErr.ExitCode() < 0 {
				ts.Fatalf("lilrae did not exit: %v", err)
			}
			last.status = exitErr.ExitCode()
		}
		if neg && last.status == 0 {
			ts.Fatalf("lilrae exited with status 0; want a failure")
		}
		if !neg && last.status != 0 {
			ts.Fatalf("lilrae exited with status %d; want 0", last.status)
		}
	}
}

// deferBinary returns the cleanup command: it runs the binary under test with
// the arguments when the script ends, also after a failure, so a case that
// starts a lab does not leave it running. A cleanup failure goes to the log;
// a case checks its own success path with its last commands.
func deferBinary(bin string) func(*testscript.TestScript, bool, []string) {
	return func(ts *testscript.TestScript, neg bool, args []string) {
		if neg || len(args) == 0 {
			ts.Fatalf("usage: cleanup ARG...")
		}
		ts.Defer(func() {
			if err := ts.Exec(bin, args...); err != nil {
				ts.Logf("cleanup: lilrae %s: %v", strings.Join(args, " "), err)
			}
		})
	}
}

// lastRunOf returns the lilrae state of the script.
func lastRunOf(ts *testscript.TestScript) *lastRun {
	last, ok := ts.Value(lastRunKey).(*lastRun)
	if !ok {
		ts.Fatalf("the script has no lilrae state")
	}
	return last
}

// lastStatus returns the exit status of the last lilrae command.
func lastStatus(ts *testscript.TestScript) int {
	last := lastRunOf(ts)
	if !last.ran {
		ts.Fatalf("no lilrae command ran")
	}
	return last.status
}

// checkStatus is the status command: the last lilrae command exited with
// status N.
func checkStatus(ts *testscript.TestScript, neg bool, args []string) {
	if neg || len(args) != 1 {
		ts.Fatalf("usage: status N")
	}
	want, err := strconv.Atoi(args[0])
	if err != nil {
		ts.Fatalf("usage: status N")
	}
	if got := lastStatus(ts); got != want {
		ts.Fatalf("the exit status is %d; want %d", got, want)
	}
}

// checkSchema returns the schema command: the JSON file conforms to the
// published schema NAME. A failure names the instance locations and the
// schema keywords, not the instance values.
func checkSchema(schemas map[string]*jsonschema.Schema) func(*testscript.TestScript, bool, []string) {
	return func(ts *testscript.TestScript, neg bool, args []string) {
		if neg || len(args) != 2 {
			ts.Fatalf("usage: schema NAME FILE")
		}
		schema, ok := schemas[args[0]]
		if !ok {
			ts.Fatalf("no published schema is named %q", args[0])
		}
		err := schema.Validate(readJSON(ts, args[1]))
		if invalid, ok := errors.AsType[*jsonschema.ValidationError](err); ok {
			ts.Fatalf("%s does not conform to %s:\n%s", args[1], args[0], strings.Join(violations(invalid), "\n"))
		}
		if err != nil {
			ts.Fatalf("validate %s: %v", args[1], err)
		}
	}
}

// violations lists the instance location and the schema keyword of each
// leaf error, and the names of missing properties, which come from the schema.
func violations(err *jsonschema.ValidationError) []string {
	if len(err.Causes) == 0 {
		line := fmt.Sprintf("  at /%s: %s", strings.Join(err.InstanceLocation, "/"), strings.Join(err.ErrorKind.KeywordPath(), "/"))
		if required, ok := err.ErrorKind.(*kind.Required); ok {
			line += " " + strings.Join(required.Missing, ", ")
		}
		return []string{line}
	}
	var out []string
	for _, cause := range err.Causes {
		out = append(out, violations(cause)...)
	}
	return out
}

// checkQuery returns the jq command: the jq query QUERY on the JSON file
// FILE gives exactly one value, true. The query can use the definitions of
// the module testdata/conformance.jq, and $status, the exit status of the
// last lilrae command, after one ran. gojq evaluates the query, so a case
// states its assertion in the jq language.
func checkQuery(modules string) func(*testscript.TestScript, bool, []string) {
	loader := gojq.WithModuleLoader(gojq.NewModuleLoader([]string{modules}))
	return func(ts *testscript.TestScript, neg bool, args []string) {
		if neg || len(args) != 2 {
			ts.Fatalf("usage: jq FILE QUERY")
		}
		code, values, err := compileQuery(ts, loader, args[1])
		if err != nil {
			ts.Fatalf("jq: %v", err)
		}
		if problem := oneTrue(code.Run(readJSON(ts, args[0]), values...)); problem != "" {
			ts.Fatalf("jq: %s on %s %s", args[1], args[0], problem)
		}
	}
}

// compileQuery compiles query with the case definitions, and with $status
// after a lilrae command ran. It returns the values of the variables.
func compileQuery(ts *testscript.TestScript, loader gojq.CompilerOption, query string) (*gojq.Code, []any, error) {
	parsed, err := gojq.Parse(`include "` + jqModule + `"; ` + query)
	if err != nil {
		return nil, nil, fmt.Errorf("parse the query: %w", err)
	}
	var names []string
	var values []any
	if last := lastRunOf(ts); last.ran {
		names, values = []string{"$status"}, []any{last.status}
	}
	code, err := gojq.Compile(parsed, loader, gojq.WithVariables(names))
	if err != nil {
		return nil, nil, fmt.Errorf("compile the query: %w", err)
	}
	return code, values, nil
}

// oneTrue returns the problem of the results of a query, or "" when they are
// exactly one value, true.
func oneTrue(results gojq.Iter) string {
	first, ok := results.Next()
	if !ok {
		return "gives no value; want true"
	}
	if err, isErr := first.(error); isErr {
		return "fails: " + err.Error()
	}
	if _, more := results.Next(); more {
		return "gives more than one value; want true"
	}
	if first != true {
		return "is not true"
	}
	return ""
}

// readJSON decodes the file name of the script, which can be stdout or
// stderr, as exactly one JSON value. The value must follow RFC 7493: valid
// UTF-8 and unique member names. The decoder of the JSON Schema library keeps
// each number exact.
func readJSON(ts *testscript.TestScript, name string) any {
	data := ts.ReadFile(name)
	if !jsontext.Value(data).IsValid() {
		ts.Fatalf("%s is not exactly one JSON value with valid UTF-8 and unique member names", name)
	}
	value, err := jsonschema.UnmarshalJSON(strings.NewReader(data))
	if err != nil {
		ts.Fatalf("decode %s: %v", name, err)
	}
	return value
}
