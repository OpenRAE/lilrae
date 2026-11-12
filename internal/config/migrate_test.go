package config

import (
	"encoding/json/jsontext"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

func TestMigrate(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		data     string
		identity *string
		want     string
	}{
		{
			name: "historical flags become profiles",
			data: `{"lab": {"name": "x"}, "containers": {"wazuh": true, "victim": false, "dns": false}, "scenario": {"identity": "tv"}}`,
			want: `{"lab": {"name": "x"}, "containers": {"profiles": ["wazuh", "kali", "enterprise", "soc", "fileshare"]}, "scenario": {"identity": "tv"}}`,
		},
		{
			name: "absent containers get the historical defaults",
			data: `{"scenario": {"identity": "tv"}}`,
			want: `{"scenario": {"identity": "tv"}, "containers": {"profiles": ["wazuh", "victim", "kali", "enterprise", "soc", "fileshare", "dns"]}}`,
		},
		{
			name:     "an explicit identity adds the scenario member",
			data:     `{"containers": {"profiles": ["soc"]}}`,
			identity: new("tv"),
			want:     `{"containers": {"profiles": ["soc"]}, "scenario": {"identity": "tv"}}`,
		},
		{
			name:     "an explicit identity replaces a null identity in place",
			data:     `{"scenario": {"source": "env-pack", "identity": null}, "containers": {"profiles": []}}`,
			identity: new("tv"),
			want:     `{"scenario": {"source": "env-pack", "identity": "tv"}, "containers": {"profiles": []}}`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			out, changed, err := Migrate([]byte(tt.data), tt.identity)
			if err != nil || !changed {
				t.Fatalf("Migrate = changed %t, %v", changed, err)
			}
			if diff := cmp.Diff(indented(t, tt.want), string(out)); diff != "" {
				t.Errorf("output (-want +got):\n%s", diff)
			}
			if _, again, err := Migrate(out, tt.identity); err != nil || again {
				t.Errorf("second Migrate = changed %t, %v; want no change", again, err)
			}
		})
	}
}

// indented returns compact JSON text in the output form of Migrate.
func indented(t *testing.T, compact string) string {
	t.Helper()
	ms, err := members([]byte(compact))
	if err != nil {
		t.Fatal(err)
	}
	v, err := encodeObject(ms)
	if err != nil {
		t.Fatal(err)
	}
	if err := v.Indent(jsontext.WithIndent("    ")); err != nil {
		t.Fatal(err)
	}
	return string(v) + "\n"
}

func TestMigrateNoChange(t *testing.T) {
	t.Parallel()
	data := `{"scenario": {"identity": "tv"}, "containers": {"profiles": ["soc"]}}`
	for _, identity := range []*string{nil, new("tv")} {
		out, changed, err := Migrate([]byte(data), identity)
		if err != nil || changed || out != nil {
			t.Errorf("Migrate(identity %v) = %q, %t, %v; want no change", identity, out, changed, err)
		}
	}
}

func TestMigrateFailures(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		data     string
		identity *string
		want     error
	}{
		{"no identity", `{"containers": {"profiles": []}}`, nil, errMigrationNoIdentity},
		{"empty identity", `{"scenario": {"identity": ""}}`, nil, errMigrationNoIdentity},
		{"explicit empty identity", `{}`, new(""), errMigrationNoIdentity},
		{"conflicting identity", `{"scenario": {"identity": "a"}}`, new("b"), errMigrationConflict},
		{"scenario not an object", `{"scenario": null}`, new("a"), errMigrationScenario},
		{"containers not an object", `{"scenario": {"identity": "a"}, "containers": []}`, nil, errMigrationContainers},
		{"mixed selection", `{"scenario": {"identity": "a"}, "containers": {"wazuh": true, "profiles": []}}`, nil, errMigrationMixed},
		{"unknown flag", `{"scenario": {"identity": "a"}, "containers": {"wazuh": true, "other": true}}`, nil, errMigrationMixed},
		{"retired mail", `{"scenario": {"identity": "a"}, "containers": {"mail": true}}`, nil, errMigrationRetired},
		{"retired reverse", `{"scenario": {"identity": "a"}, "containers": {"reverse": true}}`, nil, errMigrationRetired},
		{"flag type before retired", `{"scenario": {"identity": "a"}, "containers": {"mail": true, "dns": "yes"}}`, nil, errMigrationFlag},
		{"root not an object", `[]`, nil, errMigrationNotObject},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if _, _, err := Migrate([]byte(tt.data), tt.identity); !errors.Is(err, tt.want) {
				t.Errorf("Migrate error = %v, want %v", err, tt.want)
			}
		})
	}
}

func TestMigrateValidatesTheResult(t *testing.T) {
	t.Parallel()
	_, _, err := Migrate([]byte(`{"scenario": {"identity": "a"}, "lab": {"name": "-"}}`), nil)
	if got := fieldErrors(t, err); len(got) != 1 || got[0].Path != "lab.name" {
		t.Errorf("field errors = %v, want one at lab.name", got)
	}
}

// fakeFiles holds file contents in memory and opens each read as a new
// temporary file. A changeOnRead file gets new content after the first read.
type fakeFiles struct {
	dir          string
	files        map[string][]byte
	changeOnRead map[string][]byte
	reads        map[string]int
	replaced     bool
}

func newFakeFiles(t *testing.T, config string) *fakeFiles {
	t.Helper()
	return &fakeFiles{
		dir:   t.TempDir(),
		files: map[string][]byte{FileName: []byte(config)},
		reads: map[string]int{},
	}
}

func (f *fakeFiles) Open(name string) (*os.File, error) {
	f.reads[name]++
	data, ok := f.files[name]
	if !ok {
		return nil, fs.ErrNotExist
	}
	if next, ok := f.changeOnRead[name]; ok && f.reads[name] == 1 {
		f.files[name] = next
	}
	path := filepath.Join(f.dir, name+"."+strconv.Itoa(f.reads[name]))
	if err := os.WriteFile(path, data, 0o600); err != nil {
		return nil, fmt.Errorf("write %s: %w", name, err)
	}
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", name, err)
	}
	return file, nil
}

func (f *fakeFiles) CreateOnce(name string, data []byte) error {
	if _, ok := f.files[name]; ok {
		return fmt.Errorf("create %s: %w", name, fs.ErrExist)
	}
	f.files[name] = data
	return nil
}

func (f *fakeFiles) ReplacePrivate(name string, data []byte) error {
	f.files[name] = data
	f.replaced = true
	return nil
}

const legacyConfig = `{"scenario": {"identity": "tv"}, "containers": {"mail": false}}`

func TestMigrateFile(t *testing.T) {
	t.Parallel()
	files := newFakeFiles(t, legacyConfig)
	changed, err := MigrateFile(files, nil)
	if err != nil || !changed {
		t.Fatalf("MigrateFile = %t, %v", changed, err)
	}
	if got := string(files.files[BackupName]); got != legacyConfig {
		t.Errorf("backup = %q, want the original bytes", got)
	}
	if !strings.Contains(string(files.files[FileName]), `"profiles"`) {
		t.Errorf("aptl.json = %s, want the profiles", files.files[FileName])
	}
}

func TestMigrateFileKeepsAnEqualBackup(t *testing.T) {
	t.Parallel()
	files := newFakeFiles(t, legacyConfig)
	files.files[BackupName] = []byte(legacyConfig)
	if changed, err := MigrateFile(files, nil); err != nil || !changed {
		t.Errorf("MigrateFile = %t, %v", changed, err)
	}
}

func TestMigrateFileStops(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		setup func(*fakeFiles)
		want  error
	}{
		{"different backup", func(f *fakeFiles) { f.files[BackupName] = []byte("{}") }, errMigrationBackup},
		{"concurrent edit", func(f *fakeFiles) {
			f.changeOnRead = map[string][]byte{FileName: []byte(`{"lab": {"name": "edited"}}`)}
		}, errMigrationConcurrency},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			files := newFakeFiles(t, legacyConfig)
			tt.setup(files)
			changed, err := MigrateFile(files, nil)
			if !errors.Is(err, tt.want) || changed {
				t.Errorf("MigrateFile = %t, %v; want %v", changed, err, tt.want)
			}
			if files.replaced {
				t.Error("MigrateFile replaced aptl.json")
			}
		})
	}
}

func TestMigrateFileWithoutChangeWritesNothing(t *testing.T) {
	t.Parallel()
	files := newFakeFiles(t, `{"scenario": {"identity": "tv"}, "containers": {"profiles": []}}`)
	if changed, err := MigrateFile(files, nil); err != nil || changed {
		t.Errorf("MigrateFile = %t, %v; want no change", changed, err)
	}
	if _, ok := files.files[BackupName]; ok || files.replaced {
		t.Error("MigrateFile wrote a file")
	}
}

func TestMigrateFileOnDisk(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	writeFile(t, root, FileName, []byte(legacyConfig))
	dir, err := securefile.OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if closeErr := dir.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	})
	changed, err := MigrateFile(dir, nil)
	if err != nil || !changed {
		t.Fatalf("MigrateFile = %t, %v", changed, err)
	}
	backup, err := dir.ReadFile(BackupName)
	if err != nil || string(backup) != legacyConfig {
		t.Errorf("backup = %q, %v; want the original bytes", backup, err)
	}
	if _, err = Load(filepath.Join(root, FileName)); err != nil {
		t.Errorf("Load of the migrated file: %v", err)
	}
}

// grantsConfig returns a compact legacy configuration with n environment
// grants.
func grantsConfig(n int) string {
	grants := make([]string, n)
	for i := range grants {
		grants[i] = grant("p" + strconv.Itoa(i))
	}
	return `{"scenario": {"identity": "tv"}, "containers": {"mail": false}, "deployment": {"environment_grants": [` +
		strings.Join(grants, ",") + `]}}`
}

func TestMigrateRejectsAnOversizedResult(t *testing.T) {
	t.Parallel()
	data := grantsConfig(9000)
	if len(data) >= MaxFileSize {
		t.Fatalf("the input has %d bytes, want less than %d", len(data), MaxFileSize)
	}
	if _, _, err := Migrate([]byte(data), nil); !errors.Is(err, errTooLarge) {
		t.Errorf("Migrate error = %v, want errTooLarge", err)
	}
	files := newFakeFiles(t, data)
	if changed, err := MigrateFile(files, nil); !errors.Is(err, errTooLarge) || changed {
		t.Errorf("MigrateFile = %t, %v; want errTooLarge", changed, err)
	}
	if _, ok := files.files[BackupName]; ok || files.replaced {
		t.Error("MigrateFile wrote a file")
	}
}

func TestMigrateFileRejectsAnOversizedSource(t *testing.T) {
	t.Parallel()
	files := newFakeFiles(t, legacyConfig+strings.Repeat(" ", MaxFileSize))
	if changed, err := MigrateFile(files, nil); !errors.Is(err, errTooLarge) || changed {
		t.Errorf("MigrateFile = %t, %v; want errTooLarge", changed, err)
	}
	if _, ok := files.files[BackupName]; ok || files.replaced {
		t.Error("MigrateFile wrote a file")
	}
}

func TestMigratedFileLoads(t *testing.T) {
	t.Parallel()
	out, changed, err := Migrate([]byte(grantsConfig(100)), nil)
	if err != nil || !changed {
		t.Fatalf("Migrate = %t, %v", changed, err)
	}
	if _, err := Decode(out); err != nil {
		t.Errorf("Decode of the migrated file: %v", err)
	}
}
