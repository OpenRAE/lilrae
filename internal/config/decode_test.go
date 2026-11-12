package config

import (
	"encoding/json/v2"
	"errors"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

// fieldErrors returns the field errors of err, or fails the test.
func fieldErrors(t *testing.T, err error) []FieldError {
	t.Helper()
	var ve *ValidationError
	if !errors.As(err, &ve) {
		t.Fatalf("error = %v, want a *ValidationError", err)
	}
	return ve.Fields
}

func TestDecodeEmptyObjectGivesDefaults(t *testing.T) {
	t.Parallel()
	got, err := Decode([]byte(`{}`))
	if err != nil {
		t.Fatalf("Decode: %v", err)
	}
	if diff := cmp.Diff(Default(), got); diff != "" {
		t.Errorf("Decode({}) differs from Default() (-want +got):\n%s", diff)
	}
}

func TestDecodeFullConfiguration(t *testing.T) {
	t.Parallel()
	data := `{
		"lab": {"name": "lab-1", "network_subnet": "10.0.0.0/16"},
		"containers": {"profiles": ["wazuh", "soc"]},
		"deployment": {
			"provider": "ssh-compose", "project_name": "lab_1", "ssh_host": "h",
			"ssh_user": "u", "ssh_key": "k", "ssh_port": 2222, "remote_dir": "/r",
			"environment_grants": [{"pack": "p", "consumer": "c", "variable": "token",
				"source": {"kind": "project-env-file", "variable": "token"}}]
		},
		"scenario": {"identity": " tv ", "source": "env-pack", "pack_directory": "packs/tv"},
		"run_storage": {"backend": "local", "local_path": "./r", "s3_bucket": "b", "s3_prefix": "p/"},
		"lifecycle_policy": {"ttl_minutes": 60, "idle_timeout_minutes": 5,
			"teardown_remove_volumes": false,
			"schedule": [{"at": "08:30", "days": ["MON", "fri"], "scenario": "s"}]},
		"experiment": {"participant_action_timeout_seconds": 300,
			"participant_models": {"claude": "claude-sonnet-5", "codex": "gpt-5-nano-2025-08-07"},
			"participant_credential_sources": {
				"claude": {"kind": "process-environment", "variable": "CLAUDE_KEY"}, "codex": null}},
		"seat": {"image": "img", "public_key": "key"}
	}`
	want := Config{
		Lab:        Lab{Name: "lab-1", NetworkSubnet: "10.0.0.0/16"},
		Containers: Containers{Profiles: []string{"wazuh", "soc"}},
		Deployment: Deployment{
			Provider: "ssh-compose", ProjectName: "lab_1", SSHHost: new("h"),
			SSHUser: new("u"), SSHKey: new("k"), SSHPort: 2222, RemoteDir: new("/r"),
			EnvironmentGrants: []EnvironmentGrant{{
				Pack: "p", Consumer: "c", Variable: "token",
				Source: CredentialSource{Kind: SourceProjectEnvFile, Variable: "token"},
			}},
		},
		Scenario:   ScenarioSource{Identity: new("tv"), PackDirectory: new("packs/tv"), Source: "env-pack"},
		RunStorage: RunStorage{Backend: "local", LocalPath: "./r", S3Bucket: new("b"), S3Prefix: "p/"},
		LifecyclePolicy: &LifecyclePolicy{
			TTLMinutes: new(int64(60)), IdleTimeoutMinutes: new(int64(5)),
			Schedule: []ScheduleEntry{{At: "08:30", Days: []string{"mon", "fri"}, Scenario: new("s")}},
		},
		Experiment: Experiment{
			ParticipantActionTimeoutSeconds: 300,
			ParticipantModels:               ParticipantModels{Claude: new("claude-sonnet-5"), Codex: new("gpt-5-nano-2025-08-07")},
			ParticipantCredentialSources: ParticipantCredentialSources{
				Claude: &CredentialSource{Kind: SourceProcessEnvironment, Variable: "CLAUDE_KEY"},
			},
		},
		Seat: Seat{Image: new("img"), PublicKey: new("key")},
	}
	got, err := Decode([]byte(data))
	if err != nil {
		t.Fatalf("Decode: %v", err)
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("Decode (-want +got):\n%s", diff)
	}
}

func TestDecodePresenceRules(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		data  string
		check func(Config) bool
	}{
		{"absent profiles are unset", `{"containers": {}}`, func(c Config) bool { return c.Containers.Profiles == nil }},
		{"null profiles are unset", `{"containers": {"profiles": null}}`, func(c Config) bool { return c.Containers.Profiles == nil }},
		{"empty profiles select no group", `{"containers": {"profiles": []}}`, func(c Config) bool {
			return c.Containers.Profiles != nil && len(c.Containers.Profiles) == 0
		}},
		{"null policy is unset", `{"lifecycle_policy": null}`, func(c Config) bool { return c.LifecyclePolicy == nil }},
		{"empty policy has defaults", `{"lifecycle_policy": {}}`, func(c Config) bool {
			return c.LifecyclePolicy != nil && c.LifecyclePolicy.TeardownRemoveVolumes
		}},
		{"null optional string", `{"deployment": {"ssh_host": null}}`, func(c Config) bool { return c.Deployment.SSHHost == nil }},
		{"absent lab keeps its default name", `{"deployment": {}}`, func(c Config) bool { return c.Lab.Name == "aptl" }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := Decode([]byte(tt.data))
			if err != nil {
				t.Fatalf("Decode: %v", err)
			}
			if !tt.check(got) {
				t.Errorf("Decode(%s) = %+v", tt.data, got)
			}
		})
	}
}

// secret is a value that no error may hold.
const secret = "Zq9SECRET"

func TestDecodeRejections(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		data string
		want FieldError
	}{
		{"missing lab name", `{"lab": {}}`, FieldError{"lab.name", ruleRequired}},
		{"unknown top member", `{"extra": 1}`, FieldError{"extra", ruleUnknown}},
		{"unknown member with controls", `{"lab": {"name": "a", "\u001b]52;c;eA==\u0007": 1}}`, FieldError{"lab.<member>", ruleUnknown}},
		{"long unknown member", `{"` + strings.Repeat("k", 65) + `": 1}`, FieldError{"<member>", ruleUnknown}},
		{"unknown nested member", `{"lab": {"name": "a", "unknown_field": 1}}`, FieldError{"lab.unknown_field", ruleUnknown}},
		{"unknown source member", `{"deployment": {"environment_grants": [{"pack": "p", "consumer": "c", "variable": "v", "source": {"kind": "project-env-file", "variable": "v", "value": 1}}]}}`, FieldError{"deployment.environment_grants.0.source.value", ruleUnknown}},
		{"null object", `{"lab": null}`, FieldError{"lab", ruleNull}},
		{"null list", `{"deployment": {"environment_grants": null}}`, FieldError{"deployment.environment_grants", ruleNull}},
		{"null boolean", `{"lifecycle_policy": {"teardown_remove_volumes": null}}`, FieldError{"lifecycle_policy.teardown_remove_volumes", ruleNull}},
		{"object of wrong type", `{"lab": []}`, FieldError{"lab", ruleObject}},
		{"string of wrong type", `{"lab": {"name": 5}}`, FieldError{"lab.name", ruleString}},
		{"integral float", `{"deployment": {"ssh_port": 22.0}}`, FieldError{"deployment.ssh_port", ruleInteger}},
		{"numeric string", `{"deployment": {"ssh_port": "22"}}`, FieldError{"deployment.ssh_port", ruleInteger}},
		{"boolean integer", `{"deployment": {"ssh_port": true}}`, FieldError{"deployment.ssh_port", ruleInteger}},
		{"integer beyond 64 bits", `{"deployment": {"ssh_port": 99999999999999999999}}`, FieldError{"deployment.ssh_port", ruleInteger}},
		{"string boolean", `{"lifecycle_policy": {"teardown_remove_volumes": "yes"}}`, FieldError{"lifecycle_policy.teardown_remove_volumes", ruleBoolean}},
		{"number boolean", `{"lifecycle_policy": {"teardown_remove_volumes": 1}}`, FieldError{"lifecycle_policy.teardown_remove_volumes", ruleBoolean}},
		{"array element", `{"containers": {"profiles": ["a", 1]}}`, FieldError{"containers.profiles.1", ruleString}},
		{"grant element", `{"deployment": {"environment_grants": [1]}}`, FieldError{"deployment.environment_grants.0", ruleObject}},
		{"missing grant source", `{"deployment": {"environment_grants": [{"pack": "p", "consumer": "c", "variable": "v"}]}}`, FieldError{"deployment.environment_grants.0.source", ruleRequired}},
		{"missing source kind", `{"experiment": {"participant_credential_sources": {"claude": {"variable": "V"}}}}`, FieldError{"experiment.participant_credential_sources.claude.kind", ruleRequired}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := Decode([]byte(tt.data))
			got := fieldErrors(t, err)
			if diff := cmp.Diff([]FieldError{tt.want}, got); diff != "" {
				t.Errorf("field errors (-want +got):\n%s", diff)
			}
		})
	}
}

func TestDecodeSemanticChecks(t *testing.T) {
	t.Parallel()
	long := func(n int) string { return strings.Repeat("a", n) }
	tests := []struct {
		name string
		data string
		path string
	}{
		{"blank lab name", `{"lab": {"name": " "}}`, "lab.name"},
		{"lab name with a slash", `{"lab": {"name": "a/Zq9SECRET"}}`, "lab.name"},
		{"lab name with a final line feed", `{"lab": {"name": "aptl\n"}}`, "lab.name"},
		{"duplicate profile", `{"containers": {"profiles": ["a", "a"]}}`, "containers.profiles"},
		{"bad profile token", `{"containers": {"profiles": ["-a"]}}`, "containers.profiles"},
		{"too many profiles", `{"containers": {"profiles": [` + profileList(129) + `]}}`, "containers.profiles"},
		{"unknown provider", `{"deployment": {"provider": "Zq9SECRET"}}`, "deployment.provider"},
		{"bad project name", `{"deployment": {"project_name": "Aptl"}}`, "deployment.project_name"},
		{"duplicate grant", `{"deployment": {"environment_grants": [` + grant("p") + `,` + grant("p") + `]}}`, "deployment.environment_grants"},
		{"bad grant pack", `{"deployment": {"environment_grants": [` + grant("a/b") + `]}}`, "deployment.environment_grants.0.pack"},
		{"long grant pack", `{"deployment": {"environment_grants": [` + grant(long(129)) + `]}}`, "deployment.environment_grants.0.pack"},
		{"unknown source kind", `{"deployment": {"environment_grants": [{"pack": "p", "consumer": "c", "variable": "v", "source": {"kind": "file", "variable": "v"}}]}}`, "deployment.environment_grants.0.source.kind"},
		{"lower-case process variable", `{"experiment": {"participant_credential_sources": {"codex": {"kind": "process-environment", "variable": "key"}}}}`, "experiment.participant_credential_sources.codex.variable"},
		{"project file source for a participant", `{"experiment": {"participant_credential_sources": {"codex": {"kind": "project-env-file", "variable": "KEY"}}}}`, "experiment.participant_credential_sources.codex.kind"},
		{"empty scenario identity", `{"scenario": {"identity": "  "}}`, "scenario.identity"},
		{"scenario identity path", `{"scenario": {"identity": "a/b"}}`, "scenario.identity"},
		{"absolute scenario root", `{"scenario": {"root": "/x", "source": "project-tree"}}`, "scenario.root"},
		{"escaping scenario root", `{"scenario": {"root": "a/../..", "source": "project-tree"}}`, "scenario.root"},
		{"scenario root with NUL", `{"scenario": {"root": "a\u0000b", "source": "project-tree"}}`, "scenario.root"},
		{"pack directory in state", `{"scenario": {"pack_directory": ".aptl/packs"}}`, "scenario.pack_directory"},
		{"pack directory traversal", `{"scenario": {"pack_directory": "../x"}}`, "scenario.pack_directory"},
		{"pack directory with a tilde", `{"scenario": {"pack_directory": "~/x"}}`, "scenario.pack_directory"},
		{"pack directory with spaces", `{"scenario": {"pack_directory": " x"}}`, "scenario.pack_directory"},
		{"pack directory with a root", `{"scenario": {"pack_directory": "x", "root": "y"}}`, "scenario"},
		{"pack directory for a project tree", `{"scenario": {"pack_directory": "x", "source": "project-tree"}}`, "scenario"},
		{"unknown scenario source", `{"scenario": {"source": "git"}}`, "scenario.source"},
		{"zero ttl", `{"lifecycle_policy": {"ttl_minutes": 0}}`, "lifecycle_policy.ttl_minutes"},
		{"negative idle timeout", `{"lifecycle_policy": {"idle_timeout_minutes": -1}}`, "lifecycle_policy.idle_timeout_minutes"},
		{"bad schedule time", `{"lifecycle_policy": {"schedule": [{"at": "24:00"}]}}`, "lifecycle_policy.schedule.0.at"},
		{"schedule time with a final line feed", `{"lifecycle_policy": {"schedule": [{"at": "08:00\n"}]}}`, "lifecycle_policy.schedule.0.at"},
		{"bad weekday", `{"lifecycle_policy": {"schedule": [{"at": "08:00", "days": ["Zq9SECRET"]}]}}`, "lifecycle_policy.schedule.0.days"},
		{"zero action timeout", `{"experiment": {"participant_action_timeout_seconds": 0}}`, "experiment.participant_action_timeout_seconds"},
		{"long action timeout", `{"experiment": {"participant_action_timeout_seconds": 3601}}`, "experiment.participant_action_timeout_seconds"},
		{"mutable claude model", `{"experiment": {"participant_models": {"claude": "claude-latest"}}}`, "experiment.participant_models.claude"},
		{"undated codex model", `{"experiment": {"participant_models": {"codex": "gpt-5"}}}`, "experiment.participant_models.codex"},
		{"empty seat image", `{"seat": {"image": ""}}`, "seat.image"},
		{"long seat key", `{"seat": {"public_key": "` + long(4097) + `"}}`, "seat.public_key"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := Decode([]byte(tt.data))
			got := fieldErrors(t, err)
			if len(got) != 1 || got[0].Path != tt.path {
				t.Errorf("field errors = %v, want one at %s", got, tt.path)
			}
			if strings.Contains(err.Error(), secret) {
				t.Errorf("error %q holds a configured value", err)
			}
		})
	}
}

func TestDecodeAcceptsBoundaryValues(t *testing.T) {
	t.Parallel()
	tests := []string{
		`{"containers": {"profiles": [` + profileList(128) + `]}}`,
		`{"deployment": {"environment_grants": [{"pack": "p", "consumer": "c", "variable": "_v", "source": {"kind": "project-env-file", "variable": "lower_case"}}]}}`,
		`{"scenario": {"root": "a/b", "source": "project-tree"}}`,
		`{"experiment": {"participant_action_timeout_seconds": 1}}`,
		`{"experiment": {"participant_action_timeout_seconds": 3600}}`,
		`{"experiment": {"participant_models": {"claude": "claude-x-20250101", "codex": "o3-2025-01-01"}}}`,
		`{"lifecycle_policy": {"schedule": [{"at": "23:59", "days": []}]}}`,
		`{"seat": {"public_key": "` + strings.Repeat("é", 4096) + `"}}`,
	}
	for _, data := range tests {
		if _, err := Decode([]byte(data)); err != nil {
			t.Errorf("Decode(%.80s): %v", data, err)
		}
	}
}

func TestDecodeStrictJSON(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		data string
	}{
		{"duplicate name", `{"lab": {"name": "a", "name": "b"}}`},
		{"NaN", `{"deployment": {"ssh_port": NaN}}`},
		{"Infinity", `{"deployment": {"ssh_port": Infinity}}`},
		{"trailing data", `{} {}`},
		{"invalid UTF-8", "{\"lab\": {\"name\": \"\xff\"}}"},
		{"truncated", `{"lab":`},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if _, err := Decode([]byte(tt.data)); err == nil {
				t.Error("Decode succeeded, want an error")
			}
		})
	}
}

func TestDecodeRootMustBeObject(t *testing.T) {
	t.Parallel()
	for _, data := range []string{`[]`, `1`, `"x"`, `null`, `true`} {
		if _, err := Decode([]byte(data)); !errors.Is(err, errRootNotObject) {
			t.Errorf("Decode(%s) error = %v, want errRootNotObject", data, err)
		}
	}
}

func TestDecodeReportsEachError(t *testing.T) {
	t.Parallel()
	_, err := Decode([]byte(`{"lab": {"name": "-"}, "deployment": {"ssh_port": "x"}, "extra": 1}`))
	var paths []string
	for _, f := range fieldErrors(t, err) {
		paths = append(paths, f.Path)
	}
	want := []string{"lab.name", "deployment.ssh_port", "extra"}
	if diff := cmp.Diff(want, paths); diff != "" {
		t.Errorf("paths (-want +got):\n%s", diff)
	}
}

func TestComposeProjectNameVectors(t *testing.T) {
	t.Parallel()
	data, err := os.ReadFile("../../conformance/testdata/vectors/compose-project-name.json")
	if err != nil {
		t.Fatal(err)
	}
	var corpus struct {
		Cases []struct {
			ID     string `json:"id"`
			Input  string `json:"input"`
			Expect struct {
				Text   *string `json:"text"`
				Reject *string `json:"reject"`
			} `json:"expect"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(data, &corpus); err != nil {
		t.Fatal(err)
	}
	if len(corpus.Cases) == 0 {
		t.Fatal("the corpus has no cases")
	}
	for _, c := range corpus.Cases {
		err := CheckComposeProjectName(c.Input)
		if accepted := err == nil; accepted != (c.Expect.Text != nil) {
			t.Errorf("%s: CheckComposeProjectName error = %v, want accepted %t", c.ID, err, c.Expect.Text != nil)
		}
	}
}

func profileList(n int) string {
	items := make([]string, n)
	for i := range items {
		items[i] = `"p` + strconv.Itoa(i) + `"`
	}
	return strings.Join(items, ",")
}

func grant(pack string) string {
	return `{"pack": "` + pack + `", "consumer": "c", "variable": "v", "source": {"kind": "project-env-file", "variable": "v"}}`
}
