package config

import (
	"errors"
	"fmt"

	"github.com/OpenRAE/lilrae/internal/canonical"
)

// errRootNotObject reports a configuration whose JSON value is not an object.
var errRootNotObject = errors.New("config root must be a JSON object")

// Decode parses and validates the bytes of a configuration file. It applies
// the strict-json rules, the presence rules, and the semantic checks, and it
// returns a *ValidationError that lists each member that breaks a rule.
func Decode(data []byte) (Config, error) {
	tree, err := canonical.DecodeStrict(data)
	if err != nil {
		return Config{}, fmt.Errorf("invalid JSON: %w", err)
	}
	return decodeTree(tree)
}

// decodeTree validates a decoded JSON value.
func decodeTree(tree any) (Config, error) {
	members, ok := tree.(map[string]any)
	if !ok {
		return Config{}, errRootNotObject
	}
	r := &report{}
	cfg := decodeConfig(newObject(r, "", members))
	if err := r.err(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func decodeConfig(o *object) Config {
	cfg := Default()
	if c, ok := o.child("lab", false, false); ok {
		cfg.Lab = decodeLab(c)
	}
	if c, ok := o.child("containers", false, false); ok {
		cfg.Containers = decodeContainers(c)
	}
	if c, ok := o.child("deployment", false, false); ok {
		cfg.Deployment = decodeDeployment(c)
	}
	if c, ok := o.child("scenario", false, false); ok {
		cfg.Scenario = decodeScenario(c)
	}
	if c, ok := o.child("run_storage", false, false); ok {
		cfg.RunStorage = decodeRunStorage(c)
	}
	if c, ok := o.child("lifecycle_policy", false, true); ok {
		policy := decodeLifecyclePolicy(c)
		cfg.LifecyclePolicy = &policy
	}
	if c, ok := o.child("experiment", false, false); ok {
		cfg.Experiment = decodeExperiment(c)
	}
	if c, ok := o.child("seat", false, false); ok {
		cfg.Seat = decodeSeat(c)
	}
	o.finish()
	return cfg
}

func decodeLab(o *object) Lab {
	lab := defaultLab()
	if name, ok := o.str("name", "", true); ok {
		lab.Name = name
		o.check("name", checkLabName(name))
	}
	if subnet, ok := o.str("network_subnet", lab.NetworkSubnet, false); ok {
		lab.NetworkSubnet = subnet
	}
	o.finish()
	return lab
}

func decodeContainers(o *object) Containers {
	var c Containers
	if profiles, ok := o.optStrings("profiles"); ok {
		c.Profiles = profiles
		o.check("profiles", checkProfiles(profiles))
	}
	o.finish()
	return c
}

func decodeDeployment(o *object) Deployment {
	d := defaultDeployment()
	if provider, ok := o.str("provider", d.Provider, false); ok {
		d.Provider = provider
		o.check("provider", checkProvider(provider))
	}
	if name, ok := o.str("project_name", d.ProjectName, false); ok {
		d.ProjectName = name
		o.check("project_name", CheckComposeProjectName(name))
	}
	d.SSHHost, _ = o.optStr("ssh_host")
	d.SSHUser, _ = o.optStr("ssh_user")
	d.SSHKey, _ = o.optStr("ssh_key")
	d.SSHPort, _ = o.integer("ssh_port", d.SSHPort)
	d.RemoteDir, _ = o.optStr("remote_dir")
	d.EnvironmentGrants = decodeGrants(o)
	o.finish()
	return d
}

func decodeGrants(o *object) []EnvironmentGrant {
	elements := o.items("environment_grants")
	grants := make([]EnvironmentGrant, 0, len(elements))
	valid := true
	for _, e := range elements {
		grant, ok := decodeGrant(e)
		valid = valid && ok
		grants = append(grants, grant)
	}
	if valid {
		o.check("environment_grants", checkUniqueGrants(grants))
	}
	return grants
}

func decodeGrant(o *object) (EnvironmentGrant, bool) {
	var g EnvironmentGrant
	errorsBefore := len(o.r.fields)
	if pack, ok := o.str("pack", "", true); ok {
		g.Pack = pack
		o.check("pack", checkGrantIdentity(pack))
	}
	if consumer, ok := o.str("consumer", "", true); ok {
		g.Consumer = consumer
		o.check("consumer", checkGrantIdentity(consumer))
	}
	if variable, ok := o.str("variable", "", true); ok {
		g.Variable = variable
		o.check("variable", checkGrantVariable(variable))
	}
	if c, ok := o.child("source", true, false); ok {
		g.Source = decodeSource(c, SourceProcessEnvironment, SourceProjectEnvFile)
	}
	o.finish()
	return g, len(o.r.fields) == errorsBefore
}

// decodeSource reads a credential source descriptor whose kind is one of
// kinds.
func decodeSource(o *object, kinds ...string) CredentialSource {
	var s CredentialSource
	kind, ok := o.str("kind", "", true)
	if ok {
		o.check("kind", checkKind(kind, kinds))
		s.Kind = kind
	}
	if variable, present := o.str("variable", "", true); present {
		s.Variable = variable
		if ok {
			o.check("variable", checkSourceVariable(kind, variable))
		}
	}
	o.finish()
	return s
}

func decodeScenario(o *object) ScenarioSource {
	s := ScenarioSource{Source: "env-pack"}
	errorsBefore := len(o.r.fields)
	if identity, ok := o.optStr("identity"); ok {
		s.Identity = o.cleaned("identity", identity, checkScenarioIdentity)
	}
	if root, ok := o.optStr("root"); ok {
		s.Root = o.cleaned("root", root, checkScenarioRoot)
	}
	if dir, ok := o.optStr("pack_directory"); ok {
		s.PackDirectory = dir
		o.check("pack_directory", checkPackDirectory(*dir))
	}
	if source, ok := o.str("source", s.Source, false); ok {
		s.Source = source
		o.check("source", checkScenarioSourceKind(source))
	}
	o.finish()
	if len(o.r.fields) == errorsBefore {
		o.r.check(o.path, checkPackSource(s))
	}
	return s
}

func decodeRunStorage(o *object) RunStorage {
	rs := Default().RunStorage
	rs.Backend, _ = o.str("backend", rs.Backend, false)
	rs.LocalPath, _ = o.str("local_path", rs.LocalPath, false)
	rs.S3Bucket, _ = o.optStr("s3_bucket")
	rs.S3Prefix, _ = o.str("s3_prefix", rs.S3Prefix, false)
	o.finish()
	return rs
}

func decodeLifecyclePolicy(o *object) LifecyclePolicy {
	p := LifecyclePolicy{TeardownRemoveVolumes: true}
	if ttl, ok := o.optInteger("ttl_minutes"); ok {
		p.TTLMinutes = ttl
		o.check("ttl_minutes", checkPositiveMinutes(*ttl))
	}
	if idle, ok := o.optInteger("idle_timeout_minutes"); ok {
		p.IdleTimeoutMinutes = idle
		o.check("idle_timeout_minutes", checkPositiveMinutes(*idle))
	}
	p.TeardownRemoveVolumes = o.boolean("teardown_remove_volumes", p.TeardownRemoveVolumes)
	for _, e := range o.items("schedule") {
		p.Schedule = append(p.Schedule, decodeScheduleEntry(e))
	}
	o.finish()
	return p
}

func decodeScheduleEntry(o *object) ScheduleEntry {
	var e ScheduleEntry
	if at, ok := o.str("at", "", true); ok {
		e.At = at
		o.check("at", checkScheduleTime(at))
	}
	if days, ok := o.strings("days"); ok {
		normalized, err := normalizeWeekdays(days)
		e.Days = normalized
		o.check("days", err)
	}
	e.Scenario, _ = o.optStr("scenario")
	o.finish()
	return e
}

func decodeExperiment(o *object) Experiment {
	e := Default().Experiment
	if timeout, ok := o.integer("participant_action_timeout_seconds", e.ParticipantActionTimeoutSeconds); ok {
		e.ParticipantActionTimeoutSeconds = timeout
		o.check("participant_action_timeout_seconds", checkActionTimeout(timeout))
	}
	if c, ok := o.child("participant_models", false, false); ok {
		e.ParticipantModels = decodeParticipantModels(c)
	}
	if c, ok := o.child("participant_credential_sources", false, false); ok {
		e.ParticipantCredentialSources = decodeParticipantSources(c)
	}
	o.finish()
	return e
}

func decodeParticipantModels(o *object) ParticipantModels {
	var m ParticipantModels
	for _, provider := range []string{"claude", "codex"} {
		model, ok := o.optStr(provider)
		if !ok {
			continue
		}
		o.check(provider, checkParticipantModel(provider, *model))
		if provider == "claude" {
			m.Claude = model
		} else {
			m.Codex = model
		}
	}
	o.finish()
	return m
}

func decodeParticipantSources(o *object) ParticipantCredentialSources {
	var s ParticipantCredentialSources
	if c, ok := o.child("claude", false, true); ok {
		source := decodeSource(c, SourceProcessEnvironment)
		s.Claude = &source
	}
	if c, ok := o.child("codex", false, true); ok {
		source := decodeSource(c, SourceProcessEnvironment)
		s.Codex = &source
	}
	o.finish()
	return s
}

func decodeSeat(o *object) Seat {
	var s Seat
	if image, ok := o.optStr("image"); ok {
		s.Image = image
		o.check("image", checkLength(*image, 1, 512))
	}
	if key, ok := o.optStr("public_key"); ok {
		s.PublicKey = key
		o.check("public_key", checkLength(*key, 1, 4096))
	}
	o.finish()
	return s
}

// check records the rule that err names for a member.
func (o *object) check(name string, err error) {
	if err != nil {
		o.fail(name, err.Error())
	}
}

// check records the rule that err names for the object at path.
func (r *report) check(path string, err error) {
	if err != nil {
		r.fail(path, err.Error())
	}
}

// cleaned returns the value without surrounding whitespace after check
// accepts it, as the Python validators store it.
func (o *object) cleaned(name string, value *string, check func(string) (string, error)) *string {
	clean, err := check(*value)
	if err != nil {
		o.check(name, err)
		return value
	}
	return &clean
}
