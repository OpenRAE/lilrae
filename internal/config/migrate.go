package config

import (
	"bytes"
	"encoding/json/jsontext"
	"encoding/json/v2"
	"errors"
	"fmt"
	"io/fs"
	"maps"
	"os"
	"reflect"

	"github.com/OpenRAE/lilrae/internal/canonical"
)

// BackupName is the name of the backup that MigrateFile writes once.
const BackupName = FileName + ".bak"

// legacyFlags are the historical topology booleans of containers and their
// defaults, in the order of the Python release. They are schema history, not
// runtime defaults.
func legacyFlags() []legacyFlag {
	return []legacyFlag{
		{"wazuh", true}, {"victim", true}, {"kali", true}, {"reverse", false},
		{"enterprise", true}, {"soc", true}, {"mail", false}, {"fileshare", true},
		{"dns", true},
	}
}

type legacyFlag struct {
	name    string
	enabled bool
}

// The migration errors. None holds a configured value.
var (
	errMigrationNotObject   = errors.New("configuration must be an object")
	errMigrationScenario    = errors.New("invalid scenario configuration")
	errMigrationConflict    = errors.New("explicit scenario conflicts with existing selection")
	errMigrationNoIdentity  = errors.New("migration requires an explicit scenario identity")
	errMigrationContainers  = errors.New("invalid container configuration")
	errMigrationMixed       = errors.New("unknown or mixed container selection")
	errMigrationFlag        = errors.New("a legacy container flag must be a boolean")
	errMigrationRetired     = errors.New("retired profiles require an explicit supported replacement")
	errMigrationBackup      = errors.New("configuration backup already exists with different content")
	errMigrationConcurrency = errors.New("configuration changed during migration")
)

// Migrate converts the historical topology booleans of a configuration file
// to containers.profiles. A non-nil identity is the explicit scenario: it
// sets scenario.identity when the file has none, and it must match an
// existing identity. Migrate validates the result and
// does not change data. It reports false when the file needs no change. The
// output keeps the member order of data, with an indent of four spaces and a
// final line feed. Input and output larger than MaxFileSize are errors.
func Migrate(data []byte, identity *string) (out []byte, changed bool, err error) {
	if len(data) > MaxFileSize {
		return nil, false, errTooLarge
	}
	tree, err := canonical.DecodeStrict(data)
	if err != nil {
		return nil, false, fmt.Errorf("invalid configuration JSON: %w", err)
	}
	root, ok := tree.(map[string]any)
	if !ok {
		return nil, false, errMigrationNotObject
	}
	c, err := migration(root, identity)
	if err != nil {
		return nil, false, err
	}
	converted := applyToTree(root, c)
	if _, err = decodeTree(converted); err != nil {
		return nil, false, err
	}
	if reflect.DeepEqual(converted, tree) {
		return nil, false, nil
	}
	if out, err = applyToBytes(data, c); err != nil {
		return nil, false, err
	}
	if len(out) > MaxFileSize {
		return nil, false, errTooLarge
	}
	return out, true, nil
}

// changes are the members that a migration sets: a scenario identity and the
// operator group selection. A nil member is not set.
type changes struct {
	identity *string
	profiles []string
}

func migration(root map[string]any, identity *string) (changes, error) {
	var c changes
	scenario := map[string]any{}
	if v, present := root["scenario"]; present {
		s, ok := v.(map[string]any)
		if !ok {
			return c, errMigrationScenario
		}
		scenario = s
	}
	current := scenario["identity"]
	if identity != nil {
		if current != nil && current != *identity {
			return c, errMigrationConflict
		}
		if current == nil {
			c.identity = identity
		}
		current = *identity
	}
	if s, isString := current.(string); !isString || s == "" {
		return c, errMigrationNoIdentity
	}
	profiles, err := migratedProfiles(root)
	if err != nil {
		return c, err
	}
	c.profiles = profiles
	return c, nil
}

// migratedProfiles returns the profiles that replace the historical flags,
// or nil when containers keeps an explicit selection.
func migratedProfiles(root map[string]any) ([]string, error) {
	containers := map[string]any{}
	if v, present := root["containers"]; present {
		c, ok := v.(map[string]any)
		if !ok {
			return nil, errMigrationContainers
		}
		containers = c
	}
	flags := legacyFlags()
	historical := false
	for _, f := range flags {
		if _, present := containers[f.name]; present {
			historical = true
		}
	}
	if _, hasProfiles := containers["profiles"]; hasProfiles && !historical {
		return nil, nil
	}
	if len(containers) > countPresent(containers, flags) {
		return nil, errMigrationMixed
	}
	return enabledProfiles(containers, flags)
}

func countPresent(containers map[string]any, flags []legacyFlag) int {
	n := 0
	for _, f := range flags {
		if _, present := containers[f.name]; present {
			n++
		}
	}
	return n
}

// enabledProfiles checks every flag first and then the retired profiles, in
// the order of the Python release.
func enabledProfiles(containers map[string]any, flags []legacyFlag) ([]string, error) {
	enabled := make([]bool, len(flags))
	for i, f := range flags {
		enabled[i] = f.enabled
		if v, present := containers[f.name]; present {
			b, ok := v.(bool)
			if !ok {
				return nil, errMigrationFlag
			}
			enabled[i] = b
		}
	}
	profiles := []string{}
	for i, f := range flags {
		if enabled[i] && (f.name == "mail" || f.name == "reverse") {
			return nil, errMigrationRetired
		}
		if enabled[i] {
			profiles = append(profiles, f.name)
		}
	}
	return profiles, nil
}

// applyToTree returns a copy of root with the changes set.
func applyToTree(root map[string]any, c changes) map[string]any {
	out := make(map[string]any, len(root)+2)
	maps.Copy(out, root)
	if c.identity != nil {
		scenario := map[string]any{}
		if s, ok := root["scenario"].(map[string]any); ok {
			maps.Copy(scenario, s)
		}
		scenario["identity"] = *c.identity
		out["scenario"] = scenario
	}
	if c.profiles != nil {
		profiles := make([]any, len(c.profiles))
		for i, p := range c.profiles {
			profiles[i] = p
		}
		out["containers"] = map[string]any{"profiles": profiles}
	}
	return out
}

// applyToBytes sets the changes in the file bytes and keeps the member order.
// A new scenario member comes before a new containers member, as in Python.
func applyToBytes(data []byte, c changes) ([]byte, error) {
	top, err := members(data)
	if err != nil {
		return nil, err
	}
	if c.identity != nil {
		if top, err = setIdentity(top, *c.identity); err != nil {
			return nil, err
		}
	}
	if c.profiles != nil {
		var containers jsontext.Value
		if containers, err = json.Marshal(map[string][]string{"profiles": c.profiles}); err != nil {
			return nil, fmt.Errorf("encode profiles: %w", err)
		}
		top = setMember(top, "containers", containers)
	}
	out, err := encodeObject(top)
	if err != nil {
		return nil, err
	}
	if err := out.Indent(jsontext.WithIndent("    ")); err != nil {
		return nil, fmt.Errorf("indent configuration: %w", err)
	}
	return append(out, '\n'), nil
}

// setIdentity sets scenario.identity and keeps the other scenario members.
func setIdentity(top []member, identity string) ([]member, error) {
	var scenario []member
	for _, m := range top {
		if m.name != "scenario" {
			continue
		}
		var err error
		if scenario, err = members(m.value); err != nil {
			return nil, err
		}
	}
	name, err := json.Marshal(identity)
	if err != nil {
		return nil, fmt.Errorf("encode identity: %w", err)
	}
	value, err := encodeObject(setMember(scenario, "identity", name))
	if err != nil {
		return nil, err
	}
	return setMember(top, "scenario", value), nil
}

// member is one object member with its raw JSON value.
type member struct {
	name  string
	value jsontext.Value
}

// members returns the members of the JSON object data in order.
func members(data []byte) ([]member, error) {
	dec := jsontext.NewDecoder(bytes.NewReader(data))
	if _, err := dec.ReadToken(); err != nil {
		return nil, fmt.Errorf("read object: %w", err)
	}
	var out []member
	for dec.PeekKind() != jsontext.KindEndObject {
		name, err := dec.ReadToken()
		if err != nil {
			return nil, fmt.Errorf("read member name: %w", err)
		}
		m := member{name: name.String()}
		value, err := dec.ReadValue()
		if err != nil {
			return nil, fmt.Errorf("read member value: %w", err)
		}
		m.value = value.Clone()
		out = append(out, m)
	}
	return out, nil
}

// setMember replaces the value of the member name, or appends the member.
func setMember(ms []member, name string, value jsontext.Value) []member {
	for i := range ms {
		if ms[i].name == name {
			ms[i].value = value
			return ms
		}
	}
	return append(ms, member{name: name, value: value})
}

// encodeObject writes the members as one compact JSON object.
func encodeObject(ms []member) (jsontext.Value, error) {
	out := []byte{'{'}
	for i, m := range ms {
		if i > 0 {
			out = append(out, ',')
		}
		var err error
		if out, err = jsontext.AppendQuote(out, m.name); err != nil {
			return nil, fmt.Errorf("encode member name: %w", err)
		}
		out = append(out, ':')
		out = append(out, m.value...)
	}
	return append(out, '}'), nil
}

// Files is the file access that MigrateFile needs. A *securefile.Dir that is
// open at the project directory implements it, and it does not follow links.
type Files interface {
	Open(name string) (*os.File, error)
	CreateOnce(name string, data []byte) error
	ReplacePrivate(name string, data []byte) error
}

// readFile reads at most MaxFileSize bytes of the file name.
func readFile(files Files, name string) ([]byte, error) {
	file, err := files.Open(name)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", name, err)
	}
	data, err := readLimited(file)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	return data, nil
}

// MigrateFile migrates aptl.json in files with Migrate. It writes the exact
// original bytes to aptl.json.bak once, checks that aptl.json did not change,
// and replaces it atomically with the mode 0600. The caller holds the
// lifecycle mutation lock of the project. It reports false when the file
// needs no change.
func MigrateFile(files Files, identity *string) (bool, error) {
	original, err := readFile(files, FileName)
	if err != nil {
		return false, err
	}
	out, changed, err := Migrate(original, identity)
	if err != nil || !changed {
		return false, err
	}
	if err := commit(files, original, out); err != nil {
		return false, err
	}
	return true, nil
}

// commit writes the backup and replaces aptl.json when it did not change
// since files read original.
func commit(files Files, original, out []byte) error {
	if err := writeBackup(files, original); err != nil {
		return err
	}
	current, err := readFile(files, FileName)
	if err != nil {
		return err
	}
	if !bytes.Equal(current, original) {
		return errMigrationConcurrency
	}
	if err := files.ReplacePrivate(FileName, out); err != nil {
		return fmt.Errorf("replace %s: %w", FileName, err)
	}
	return nil
}

// writeBackup writes the original bytes once. An existing backup with the
// same bytes is the backup of an earlier attempt.
func writeBackup(files Files, original []byte) error {
	err := files.CreateOnce(BackupName, original)
	if err == nil {
		return nil
	}
	if !errors.Is(err, fs.ErrExist) {
		return fmt.Errorf("write %s: %w", BackupName, err)
	}
	backup, err := readFile(files, BackupName)
	if err != nil {
		return err
	}
	if !bytes.Equal(backup, original) {
		return errMigrationBackup
	}
	return nil
}
