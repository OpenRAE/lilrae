// Package config decodes, validates, finds, and migrates aptl.json, the
// durable non-secret configuration of a LilRAE project (ADR-025).
//
// Each object rejects an unknown member. An absent member gets its default,
// and only an optional member accepts null. The types marshal with
// encoding/json/v2 in the member order of the Python model, with null for an
// unset optional member, so they also give the resolved form that
// "lilrae config show --json" prints.
package config

import (
	"bytes"
	"encoding/json/jsontext"
	"errors"
	"fmt"
	"io"
	"maps"
	"net/netip"
	"os"
	"path/filepath"
	"slices"
)

// FileName is the name of the configuration file in a project directory.
const FileName = "aptl.json"

// MaxFileSize is the largest configuration file that Load reads. The
// largest bounded members are 128 profiles of 128 characters and a seat key
// of 4096 characters, so the limit leaves room for about 1,500 environment
// grants.
const MaxFileSize = 1 << 20

// The credential source kinds of a descriptor.
const (
	SourceProcessEnvironment     = "process-environment"
	SourceProjectEnvFile         = "project-env-file"
	SourceAttachedServiceAccount = "attached-service-account"
)

// MCPServerIDs returns the servers of the operator MCP catalog, in catalog
// order. They are the default operator ceiling of the mcp member, and the
// catalog of the Python release (core/participant_mcp_policy.json) is their
// source.
func MCPServerIDs() []string {
	return []string{"aptl-red", "aptl-indexer", "aptl-wazuh", "aptl-network", "aptl-soar", "aptl-threatintel"}
}

// Config is the resolved project configuration.
type Config struct {
	Lab             Lab              `json:"lab"`
	Containers      Containers       `json:"containers"`
	Deployment      Deployment       `json:"deployment"`
	Scenario        ScenarioSource   `json:"scenario"`
	RunStorage      RunStorage       `json:"run_storage"`
	LifecyclePolicy *LifecyclePolicy `json:"lifecycle_policy"`
	Experiment      Experiment       `json:"experiment"`
	Seat            Seat             `json:"seat"`
	MCP             MCPPolicy        `json:"mcp"`
}

// Lab holds the lab-level settings.
type Lab struct {
	Name          string `json:"name"`
	NetworkSubnet string `json:"network_subnet"`
}

// Containers holds the selection from the operator groups of the admitted
// scenario. A nil Profiles is unset and marshals as null, and an empty list
// selects no group.
type Containers struct {
	Profiles *[]string `json:"profiles"`
}

// Deployment selects the deployment backend. RangeEgressAllowances are the
// exact external destinations that the operator grants to the native range,
// and EnvironmentGrants are the operator grants of configured sources to
// declared scenario variables.
type Deployment struct {
	RangeEgressAllowances []RangeEgressAllowance `json:"range_egress_allowances"`
	Provider              string                 `json:"provider"`
	ProjectName           string                 `json:"project_name"`
	SSHHost               *string                `json:"ssh_host"`
	SSHUser               *string                `json:"ssh_user"`
	SSHKey                *string                `json:"ssh_key"`
	SSHPort               int64                  `json:"ssh_port"`
	RemoteDir             *string                `json:"remote_dir"`
	EnvironmentGrants     []EnvironmentGrant     `json:"environment_grants"`
}

// RangeEgressAllowance is one exact unicast destination address and
// transport port. Protocol is tcp or udp.
type RangeEgressAllowance struct {
	Destination string `json:"destination"`
	Protocol    string `json:"protocol"`
	Port        int64  `json:"port"`
}

// EnvironmentGrant grants one configured source to one declared variable of
// one pack node. It holds locators, never a value.
type EnvironmentGrant struct {
	Pack     string           `json:"pack"`
	Consumer string           `json:"consumer"`
	Variable string           `json:"variable"`
	Source   CredentialSource `json:"source"`
}

// CredentialSource selects one exact variable of a source without its value.
// Kind is SourceProcessEnvironment or SourceProjectEnvFile.
type CredentialSource struct {
	Kind     string `json:"kind"`
	Variable string `json:"variable"`
}

// ScenarioSource selects the scenario and the source of its bytes.
type ScenarioSource struct {
	Identity      *string `json:"identity"`
	Root          *string `json:"root"`
	PackDirectory *string `json:"pack_directory"`
	Source        string  `json:"source"`
}

// RunStorage configures the experiment run storage.
type RunStorage struct {
	Backend   string  `json:"backend"`
	LocalPath string  `json:"local_path"`
	S3Bucket  *string `json:"s3_bucket"`
	S3Prefix  string  `json:"s3_prefix"`
}

// LifecyclePolicy is the ephemeral lifecycle policy of the range (DEP-003).
type LifecyclePolicy struct {
	TTLMinutes            *int64          `json:"ttl_minutes"`
	IdleTimeoutMinutes    *int64          `json:"idle_timeout_minutes"`
	TeardownRemoveVolumes bool            `json:"teardown_remove_volumes"`
	Schedule              []ScheduleEntry `json:"schedule"`
}

// ScheduleEntry is one provisioning window. At is a UTC HH:MM time, and Days
// holds lower-case weekday names, with no names for each day.
type ScheduleEntry struct {
	At       string   `json:"at"`
	Days     []string `json:"days"`
	Scenario *string  `json:"scenario"`
}

// Experiment holds the non-secret apparatus settings of an experiment.
// ParticipantServingProviders maps a trial model to its approved OpenRouter
// serving provider, and OpencodeExecutable is the absolute path of the
// installed OpenCode executable.
type Experiment struct {
	ParticipantActionTimeoutSeconds int64                        `json:"participant_action_timeout_seconds"`
	ParticipantModels               ParticipantModels            `json:"participant_models"`
	ParticipantCredentialSources    ParticipantCredentialSources `json:"participant_credential_sources"`
	ParticipantServingProviders     ServingProviders             `json:"participant_serving_providers"`
	OpencodeExecutable              *string                      `json:"opencode_executable"`
}

// ServingProviders maps a trial model to its serving provider. It marshals
// as one object with the models in sorted order.
type ServingProviders map[string]string

// MarshalJSONTo writes the object with the models in sorted order, so the
// resolved form does not depend on map iteration.
func (p ServingProviders) MarshalJSONTo(enc *jsontext.Encoder) error {
	tokens := []jsontext.Token{jsontext.BeginObject}
	for _, model := range slices.Sorted(maps.Keys(p)) {
		tokens = append(tokens, jsontext.String(model), jsontext.String(p[model]))
	}
	tokens = append(tokens, jsontext.EndObject)
	for _, token := range tokens {
		if err := enc.WriteToken(token); err != nil {
			return fmt.Errorf("participant serving providers: %w", err)
		}
	}
	return nil
}

// ParticipantModels selects the model of each installed provider.
type ParticipantModels struct {
	Claude   *string `json:"claude"`
	Codex    *string `json:"codex"`
	Opencode *string `json:"opencode"`
}

// ParticipantCredentialSources selects the credential source of each
// installed provider. The claude, codex, and opencode sources have the kind
// SourceProcessEnvironment.
type ParticipantCredentialSources struct {
	Claude   *CredentialSource `json:"claude"`
	Codex    *CredentialSource `json:"codex"`
	Opencode *CredentialSource `json:"opencode"`
	Vertex   *VertexSource     `json:"vertex"`
}

// VertexSource selects the Google Cloud credential of the Vertex AI models.
// Kind SourceProcessEnvironment names a Variable that holds a service account
// key. Kind SourceAttachedServiceAccount names the Project of the attached
// service account of the host, which has no key material.
type VertexSource struct {
	Kind     string  `json:"kind"`
	Variable *string `json:"variable,omitzero"`
	Project  *string `json:"project,omitzero"`
}

// MCPPolicy is the operator ceiling of the participant MCP servers. A
// required server must also be allowed, and each server must be in
// MCPServerIDs.
type MCPPolicy struct {
	AllowedServers  []string `json:"allowed_servers"`
	RequiredServers []string `json:"required_servers"`
}

// Seat selects the seat VM image and its signing trust.
type Seat struct {
	Image     *string `json:"image"`
	PublicKey *string `json:"public_key"`
}

// Default returns the configuration of an empty aptl.json object.
func Default() Config {
	return Config{
		Lab:        defaultLab(),
		Deployment: defaultDeployment(),
		Scenario:   ScenarioSource{Source: "env-pack"},
		RunStorage: RunStorage{Backend: "local", LocalPath: "./runs", S3Prefix: "runs/"},
		Experiment: Experiment{ParticipantActionTimeoutSeconds: 120, ParticipantServingProviders: ServingProviders{}},
		MCP:        defaultMCPPolicy(),
	}
}

func defaultMCPPolicy() MCPPolicy {
	return MCPPolicy{AllowedServers: MCPServerIDs(), RequiredServers: []string{}}
}

// defaultLab returns the lab defaults. The subnet is the default of the
// Python model, and lab.network_subnet in aptl.json replaces it.
func defaultLab() Lab {
	subnet := netip.PrefixFrom(netip.AddrFrom4([4]byte{172, 20, 0, 0}), 16)
	return Lab{Name: "aptl", NetworkSubnet: subnet.String()}
}

func defaultDeployment() Deployment {
	return Deployment{Provider: "docker-compose", ProjectName: "aptl", SSHPort: 22}
}

// Find returns the path of aptl.json in dir. It checks only dir, and it
// follows a link, as the Python release does. It reports false when dir has
// no regular aptl.json.
func Find(dir string) (string, bool) {
	path := filepath.Join(dir, FileName)
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() {
		return "", false
	}
	return path, true
}

// Load reads and validates the configuration file at path. It reads at most
// MaxFileSize bytes. The error for a missing file matches the ErrNotExist
// error of the fs package. Each error names the file and holds no configured
// value.
func Load(path string) (Config, error) {
	data, err := readBounded(path)
	if err != nil {
		return Config{}, err
	}
	cfg, err := Decode(data)
	if err != nil {
		return Config{}, fmt.Errorf("%s: %w", path, err)
	}
	return cfg, nil
}

func readBounded(path string) (data []byte, err error) {
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("open config file: %w", err)
	}
	if data, err = readLimited(file); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if len(bytes.TrimSpace(data)) == 0 {
		return nil, fmt.Errorf("config file is empty: %s", path)
	}
	return data, nil
}

// errTooLarge reports a configuration larger than MaxFileSize.
var errTooLarge = fmt.Errorf("the configuration is larger than %d bytes", MaxFileSize)

// readLimited reads at most MaxFileSize bytes of file and closes it.
func readLimited(file *os.File) (data []byte, err error) {
	defer func() { err = errors.Join(err, file.Close()) }()
	data, err = io.ReadAll(io.LimitReader(file, MaxFileSize+1))
	if err != nil {
		return nil, fmt.Errorf("read configuration: %w", err)
	}
	if tooLarge(data) {
		return nil, errTooLarge
	}
	return data, nil
}

// tooLarge reports whether data is larger than MaxFileSize.
func tooLarge(data []byte) bool {
	return len(data) > MaxFileSize
}
