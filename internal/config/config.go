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
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
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
	SourceProcessEnvironment = "process-environment"
	SourceProjectEnvFile     = "project-env-file"
)

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
}

// Lab holds the lab-level settings.
type Lab struct {
	Name          string `json:"name"`
	NetworkSubnet string `json:"network_subnet"`
}

// Containers holds the selection from the operator groups of the admitted
// scenario. A nil Profiles is unset, and an empty Profiles selects no group.
type Containers struct {
	Profiles []string `json:"profiles,format:emitnull"`
}

// Deployment selects the deployment backend. EnvironmentGrants are the
// operator grants of configured sources to declared scenario variables.
type Deployment struct {
	Provider          string             `json:"provider"`
	ProjectName       string             `json:"project_name"`
	SSHHost           *string            `json:"ssh_host"`
	SSHUser           *string            `json:"ssh_user"`
	SSHKey            *string            `json:"ssh_key"`
	SSHPort           int64              `json:"ssh_port"`
	RemoteDir         *string            `json:"remote_dir"`
	EnvironmentGrants []EnvironmentGrant `json:"environment_grants"`
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
type Experiment struct {
	ParticipantActionTimeoutSeconds int64                        `json:"participant_action_timeout_seconds"`
	ParticipantModels               ParticipantModels            `json:"participant_models"`
	ParticipantCredentialSources    ParticipantCredentialSources `json:"participant_credential_sources"`
}

// ParticipantModels selects the model of each installed provider.
type ParticipantModels struct {
	Claude *string `json:"claude"`
	Codex  *string `json:"codex"`
}

// ParticipantCredentialSources selects the credential source of each
// installed provider. Each source has the kind SourceProcessEnvironment.
type ParticipantCredentialSources struct {
	Claude *CredentialSource `json:"claude"`
	Codex  *CredentialSource `json:"codex"`
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
		Experiment: Experiment{ParticipantActionTimeoutSeconds: 120},
	}
}

func defaultLab() Lab {
	return Lab{Name: "aptl", NetworkSubnet: "172.20.0.0/16"}
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
// MaxFileSize bytes. A missing file is an error that matches
// [fs.ErrNotExist]. Each error names the file and holds no configured value.
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
	if len(data) > MaxFileSize {
		return nil, errTooLarge
	}
	return data, nil
}
