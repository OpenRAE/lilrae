package conformance_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"

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
	bin := binary(t)
	schemas := loadSchemas(t)
	testscript.Run(t, testscript.Params{
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
			"lilrae":        runBinary(bin),
			"status":        checkStatus,
			"envelope":      checkEnvelope,
			"schema":        checkSchema(schemas),
			"field":         checkField,
			"doctor-counts": checkDoctorCounts,
		},
	})
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

// checkEnvelope is the envelope command: the standard output of the last
// lilrae command is one JSON object with the command, schema_version 1, and
// an ok that is true exactly when the exit status is 0.
func checkEnvelope(ts *testscript.TestScript, neg bool, args []string) {
	if neg || len(args) != 1 {
		ts.Fatalf("usage: envelope COMMAND")
	}
	object := readObject(ts, "stdout")
	if object["command"] != args[0] {
		ts.Fatalf("the command field is not %q", args[0])
	}
	if version, ok := object["schema_version"].(json.Number); !ok || version.String() != "1" {
		ts.Fatalf("schema_version is not 1")
	}
	okField, isBool := object["ok"].(bool)
	if !isBool {
		ts.Fatalf("ok is not a boolean")
	}
	if status := lastStatus(ts); okField != (status == 0) {
		ts.Fatalf("ok is %t, but the exit status is %d", okField, status)
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

// checkField is the field command: the value at a JSON Pointer (RFC 6901) of
// the JSON file equals the JSON value. With a negation, the value exists and
// differs. It compares parsed values, so the layout of the file does not
// matter.
func checkField(ts *testscript.TestScript, neg bool, args []string) {
	if len(args) != 3 {
		ts.Fatalf("usage: field FILE POINTER JSON")
	}
	want, err := jsonschema.UnmarshalJSON(strings.NewReader(args[2]))
	if err != nil {
		ts.Fatalf("field: %q is not a JSON value", args[2])
	}
	got, ok := lookup(readJSON(ts, args[0]), args[1])
	if !ok {
		ts.Fatalf("%s has no value at %s", args[0], args[1])
	}
	if equal := reflect.DeepEqual(got, want); equal == neg {
		ts.Fatalf("the value at %s of %s does not match %s", args[1], args[0], args[2])
	}
}

// lookup returns the value at the JSON Pointer of doc.
func lookup(doc any, pointer string) (any, bool) {
	if pointer == "" {
		return doc, true
	}
	if !strings.HasPrefix(pointer, "/") {
		return nil, false
	}
	value := doc
	for token := range strings.SplitSeq(pointer[1:], "/") {
		token = strings.ReplaceAll(strings.ReplaceAll(token, "~1", "/"), "~0", "~")
		switch node := value.(type) {
		case map[string]any:
			next, ok := node[token]
			if !ok {
				return nil, false
			}
			value = next
		case []any:
			index, err := strconv.Atoi(token)
			if err != nil || index < 0 || index >= len(node) {
				return nil, false
			}
			value = node[index]
		default:
			return nil, false
		}
	}
	return value, true
}

// checkDoctorCounts is the doctor-counts command: the counts of a doctor
// result equal the number of checks with each status, and the last exit
// status is 0 exactly when no check failed.
func checkDoctorCounts(ts *testscript.TestScript, neg bool, args []string) {
	if neg || len(args) != 1 {
		ts.Fatalf("usage: doctor-counts FILE")
	}
	object := readObject(ts, args[0])
	checks, isList := object["checks"].([]any)
	counts, isObject := object["counts"].(map[string]any)
	if !isList || !isObject {
		ts.Fatalf("the doctor result has no checks list or counts object")
	}
	tally := map[string]int{}
	for _, check := range checks {
		entry, isObject := check.(map[string]any)
		status, isString := entry["status"].(string)
		if !isObject || !isString {
			ts.Fatalf("a doctor check has no status")
		}
		tally[status]++
	}
	for _, status := range []string{"pass", "warn", "fail", "skip"} {
		count, isNumber := counts[status].(json.Number)
		if !isNumber || count.String() != strconv.Itoa(tally[status]) {
			ts.Fatalf("counts.%s does not equal the number of %s checks", status, status)
		}
	}
	if (tally["fail"] == 0) != (lastStatus(ts) == 0) {
		ts.Fatalf("the exit status is %d with %d failed checks", lastStatus(ts), tally["fail"])
	}
}

// readJSON decodes the file name of the script, which can be stdout or
// stderr, as exactly one JSON value.
func readJSON(ts *testscript.TestScript, name string) any {
	value, err := jsonschema.UnmarshalJSON(strings.NewReader(ts.ReadFile(name)))
	if err != nil {
		ts.Fatalf("%s is not exactly one JSON value", name)
	}
	return value
}

func readObject(ts *testscript.TestScript, name string) map[string]any {
	object, ok := readJSON(ts, name).(map[string]any)
	if !ok {
		ts.Fatalf("%s is not a JSON object", name)
	}
	return object
}
