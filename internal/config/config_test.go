package config

import (
	"bytes"
	"encoding/json/v2"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func writeFile(t *testing.T, dir, name string, data []byte) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestFind(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if _, ok := Find(dir); ok {
		t.Error("Find found aptl.json in an empty directory")
	}
	path := writeFile(t, dir, FileName, []byte(`{}`))
	if got, ok := Find(dir); !ok || got != path {
		t.Errorf("Find = %q, %t; want %q, true", got, ok, path)
	}
	if _, ok := Find(filepath.Join(dir, "missing")); ok {
		t.Error("Find found aptl.json in a missing directory")
	}
}

func TestFindChecksOnlyTheDirectory(t *testing.T) {
	t.Parallel()
	parent := t.TempDir()
	writeFile(t, parent, FileName, []byte(`{}`))
	child := filepath.Join(parent, "child")
	if err := os.Mkdir(child, 0o700); err != nil {
		t.Fatal(err)
	}
	if _, ok := Find(child); ok {
		t.Error("Find searched an ancestor")
	}
}

func TestFindRefusesADirectory(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, FileName), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, ok := Find(dir); ok {
		t.Error("Find accepted a directory")
	}
}

func TestLoad(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := writeFile(t, dir, FileName, []byte(`{"lab": {"name": "x"}}`))
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Lab.Name != "x" {
		t.Errorf("Lab.Name = %q, want x", cfg.Lab.Name)
	}
}

func TestLoadFailures(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	tests := []struct {
		name string
		data []byte
	}{
		{"empty", nil},
		{"blank", []byte(" \n\t")},
		{"too large", append([]byte(`{"lab": {"name": "a"}}`), bytes.Repeat([]byte(" "), MaxFileSize)...)},
		{"invalid JSON", []byte(`{"lab":`)},
		{"invalid member", []byte(`{"lab": {"name": "-"}}`)},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			path := writeFile(t, dir, strings.ReplaceAll(tt.name, " ", "-")+".json", tt.data)
			_, err := Load(path)
			if err == nil {
				t.Fatal("Load succeeded, want an error")
			}
			if !strings.Contains(err.Error(), path) {
				t.Errorf("error %q does not name the file", err)
			}
		})
	}
}

func TestLoadAcceptsTheLargestFile(t *testing.T) {
	t.Parallel()
	data := []byte(`{"lab": {"name": "a"}}`)
	data = append(data, bytes.Repeat([]byte(" "), MaxFileSize-len(data))...)
	path := writeFile(t, t.TempDir(), FileName, data)
	if _, err := Load(path); err != nil {
		t.Errorf("Load of %d bytes: %v", len(data), err)
	}
}

func TestLoadMissingFile(t *testing.T) {
	t.Parallel()
	_, err := Load(filepath.Join(t.TempDir(), FileName))
	if !errors.Is(err, fs.ErrNotExist) {
		t.Errorf("Load error = %v, want fs.ErrNotExist", err)
	}
}

// TestResolvedForm checks the JSON value of the defaults against the Python
// model_dump(mode="json") of an empty configuration, in member order.
func TestResolvedForm(t *testing.T) {
	t.Parallel()
	want := `{"lab":{"name":"aptl","network_subnet":"172.20.0.0/16"},` +
		`"containers":{"profiles":null},` +
		`"deployment":{"provider":"docker-compose","project_name":"aptl","ssh_host":null,` +
		`"ssh_user":null,"ssh_key":null,"ssh_port":22,"remote_dir":null,"environment_grants":[]},` +
		`"scenario":{"identity":null,"root":null,"pack_directory":null,"source":"env-pack"},` +
		`"run_storage":{"backend":"local","local_path":"./runs","s3_bucket":null,"s3_prefix":"runs/"},` +
		`"lifecycle_policy":null,` +
		`"experiment":{"participant_action_timeout_seconds":120,` +
		`"participant_models":{"claude":null,"codex":null},` +
		`"participant_credential_sources":{"claude":null,"codex":null}},` +
		`"seat":{"image":null,"public_key":null}}`
	got, err := json.Marshal(Default())
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(want, string(got)); diff != "" {
		t.Errorf("resolved form (-want +got):\n%s", diff)
	}
}

func TestResolvedFormOfSetMembers(t *testing.T) {
	t.Parallel()
	cfg, err := Decode([]byte(`{"containers": {"profiles": []}, "lifecycle_policy": {"schedule": [{"at": "08:00"}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	got, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		`"containers":{"profiles":[]}`,
		`"lifecycle_policy":{"ttl_minutes":null,"idle_timeout_minutes":null,"teardown_remove_volumes":true,"schedule":[{"at":"08:00","days":[],"scenario":null}]}`,
	} {
		if !strings.Contains(string(got), want) {
			t.Errorf("resolved form %s does not hold %s", got, want)
		}
	}
}
