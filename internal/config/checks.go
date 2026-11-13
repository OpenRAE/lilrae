package config

import (
	"errors"
	"net/netip"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

// The patterns of the Python validators. Go anchors with \A and \z, so a
// final line feed does not match, as it does before $ in Python.
var (
	labNamePattern            = regexp.MustCompile(`\A[a-zA-Z0-9][a-zA-Z0-9._-]*\z`)
	composeProjectNamePattern = regexp.MustCompile(`\A[a-z0-9][a-z0-9_-]{0,62}\z`)
	profilePattern            = regexp.MustCompile(`\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\z`)
	scenarioIdentityPattern   = regexp.MustCompile(`\A[a-z0-9][a-z0-9._-]*\z`)
	grantIdentityPattern      = regexp.MustCompile(`\A[a-zA-Z0-9][a-zA-Z0-9._-]*\z`)
	environmentNamePattern    = regexp.MustCompile(`\A[A-Za-z_][A-Za-z0-9_]{0,127}\z`)
	processVariablePattern    = regexp.MustCompile(`\A[A-Z_][A-Z0-9_]{0,127}\z`)
	scheduleTimePattern       = regexp.MustCompile(`\A([01]\d|2[0-3]):[0-5]\d\z`)
	participantModelPattern   = regexp.MustCompile(`\A[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,127}\z`)
	claudeModelPattern        = regexp.MustCompile(`\Aclaude-(?:[a-z0-9-]+[-@][0-9]{8}|(?:sonnet|opus|haiku)-[1-9][a-z0-9.-]*)\z`)
	codexModelPattern         = regexp.MustCompile(`\A(?:codex-[a-z0-9._-]+|gpt-[a-z0-9._-]+|o[0-9][a-z0-9._-]*)\z`)
	opencodeModelPattern      = regexp.MustCompile(`\A(?:openrouter|google-vertex)/[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,112}\z`)
	googleProjectPattern      = regexp.MustCompile(`\A[a-z][a-z0-9-]{4,28}[a-z0-9]\z`)
)

// maxServingProviders is the largest number of trial models that
// experiment.participant_serving_providers can map.
const maxServingProviders = 64

// errUnknownSourceKind reports a credential source kind outside the kinds of
// a member.
var errUnknownSourceKind = errors.New("unknown credential source kind")

// CheckComposeProjectName reports whether name is a Compose project name of
// 1 to 63 lower-case letters, digits, hyphens, or underscores that starts with
// a letter or a digit.
func CheckComposeProjectName(name string) error {
	if !composeProjectNamePattern.MatchString(name) {
		return errors.New("must be 1-63 lowercase letters, digits, hyphens, or underscores and start with a letter or digit")
	}
	return nil
}

func checkLabName(name string) error {
	if strings.TrimFunc(name, isPythonSpace) == "" {
		return errors.New("lab name must not be empty")
	}
	if !labNamePattern.MatchString(name) {
		return errors.New("lab name must use only letters, digits, dots, hyphens, and underscores, and start with a letter or digit")
	}
	return nil
}

func checkProfiles(profiles []string) error {
	invalid := len(profiles) > 128 || hasDuplicate(profiles) ||
		slices.ContainsFunc(profiles, func(p string) bool { return !profilePattern.MatchString(p) })
	if invalid {
		return errors.New("invalid operator group selection")
	}
	return nil
}

func hasDuplicate(values []string) bool {
	seen := make(map[string]bool, len(values))
	for _, v := range values {
		if seen[v] {
			return true
		}
		seen[v] = true
	}
	return false
}

func checkProvider(provider string) error {
	if provider != "docker-compose" && provider != "ssh-compose" {
		return errors.New("unknown deployment provider; supported: docker-compose, ssh-compose")
	}
	return nil
}

func checkGrantIdentity(value string) error {
	if err := checkLength(value, 1, 128); err != nil {
		return err
	}
	if !grantIdentityPattern.MatchString(value) {
		return errors.New("environment grant pack or consumer is invalid")
	}
	return nil
}

// checkGrantVariable checks a grant variable. The pattern limits it to 128
// characters.
func checkGrantVariable(value string) error {
	if !environmentNamePattern.MatchString(value) {
		return errors.New("environment grant variable is invalid")
	}
	return nil
}

func checkKind(kind string, kinds []string) error {
	if !slices.Contains(kinds, kind) {
		return errUnknownSourceKind
	}
	return nil
}

// checkSourceVariable checks the variable locator of a source of a known
// kind. Each pattern limits it to 128 characters.
func checkSourceVariable(kind, variable string) error {
	pattern := environmentNamePattern
	if kind == SourceProcessEnvironment {
		pattern = processVariablePattern
	}
	if !pattern.MatchString(variable) {
		return errors.New("credential source variable is invalid")
	}
	return nil
}

func checkUniqueGrants(grants []EnvironmentGrant) error {
	type key struct{ pack, consumer, variable string }
	seen := make(map[key]bool, len(grants))
	for _, g := range grants {
		k := key{g.Pack, g.Consumer, g.Variable}
		if seen[k] {
			return errors.New("environment grants must be unique per variable")
		}
		seen[k] = true
	}
	return nil
}

func checkScenarioIdentity(value string) (string, error) {
	clean := strings.TrimFunc(value, isPythonSpace)
	if clean == "" {
		return "", errors.New("scenario identity must not be empty")
	}
	if !scenarioIdentityPattern.MatchString(clean) {
		return "", errors.New("invalid scenario identity")
	}
	return clean, nil
}

func checkScenarioRoot(value string) (string, error) {
	clean := strings.TrimFunc(value, isPythonSpace)
	if clean == "" {
		return "", errors.New("scenario root must not be empty")
	}
	if strings.ContainsRune(clean, 0) {
		return "", errors.New("scenario root must not contain a NUL byte")
	}
	if strings.HasPrefix(clean, "/") || slices.Contains(strings.Split(clean, "/"), "..") {
		return "", errors.New("scenario root must be a relative path contained by the project")
	}
	return clean, nil
}

func checkPackDirectory(value string) error {
	invalid := securefile.CheckPath(value) != nil ||
		value != strings.TrimFunc(value, isPythonSpace) ||
		strings.ContainsAny(value, `~$\`) ||
		strings.SplitN(value, "/", 2)[0] == ".aptl"
	if invalid {
		return errors.New("invalid pack directory locator")
	}
	return nil
}

func checkScenarioSourceKind(source string) error {
	if source != "project-tree" && source != "env-pack" {
		return errors.New("scenario source must be project-tree or env-pack")
	}
	return nil
}

func checkPackSource(s ScenarioSource) error {
	if s.PackDirectory != nil && (s.Source != "env-pack" || s.Root != nil) {
		return errors.New("pack_directory requires env-pack without root")
	}
	return nil
}

func checkPositiveMinutes(minutes int64) error {
	if minutes <= 0 {
		return errors.New("must be a positive number of minutes")
	}
	return nil
}

func checkScheduleTime(at string) error {
	if !scheduleTimePattern.MatchString(at) {
		return errors.New("schedule time must be a 24-hour HH:MM UTC time")
	}
	return nil
}

// normalizeWeekdays returns the weekday names in lower case.
func normalizeWeekdays(days []string) ([]string, error) {
	out := make([]string, 0, len(days))
	for _, day := range days {
		lower := strings.ToLower(day)
		if !isWeekday(lower) {
			return days, errors.New("invalid weekday; use mon, tue, wed, thu, fri, sat, or sun")
		}
		out = append(out, lower)
	}
	return out, nil
}

func isWeekday(day string) bool {
	switch day {
	case "mon", "tue", "wed", "thu", "fri", "sat", "sun":
		return true
	}
	return false
}

func checkActionTimeout(seconds int64) error {
	if seconds < 1 || seconds > 3600 {
		return errors.New("must be from 1 to 3600")
	}
	return nil
}

func checkParticipantModel(provider, model string) error {
	if checkLength(model, 0, 128) != nil ||
		!participantModelPattern.MatchString(model) ||
		!immutableModelPattern(provider).MatchString(model) {
		return errors.New("installed participant model identifier is invalid")
	}
	return nil
}

// immutableModelPattern returns the pattern of the model names of an
// installed provider, which is claude, codex, or opencode.
func immutableModelPattern(provider string) *regexp.Regexp {
	switch provider {
	case "claude":
		return claudeModelPattern
	case "codex":
		return codexModelPattern
	}
	return opencodeModelPattern
}

func checkGoogleProject(project string) error {
	if checkLength(project, 6, 30) != nil || !googleProjectPattern.MatchString(project) {
		return errors.New("attached service account project is invalid")
	}
	return nil
}

// checkOpencodeExecutable admits an absolute path of 2 to 4096 characters,
// as the path rules of the host decide.
func checkOpencodeExecutable(path string) error {
	if err := checkLength(path, 2, 4096); err != nil {
		return err
	}
	if !filepath.IsAbs(path) {
		return errors.New("opencode_executable must be an absolute path")
	}
	return nil
}

// normalizeEgressDestination returns the canonical text of an exact unicast
// address. An IPv4-mapped address is loopback, multicast, or unspecified when
// its IPv4 address is, as in the Python release.
func normalizeEgressDestination(destination string) (string, error) {
	address, err := netip.ParseAddr(destination)
	if err != nil {
		return destination, errors.New("egress destination must be an IP address")
	}
	ipv4 := address.Unmap()
	if ipv4.IsLoopback() || ipv4.IsMulticast() || ipv4.IsUnspecified() {
		return destination, errors.New("egress destination must be an exact unicast IP address")
	}
	return address.String(), nil
}

func checkTransport(protocol string) error {
	if protocol != "tcp" && protocol != "udp" {
		return errors.New("protocol must be tcp or udp")
	}
	return nil
}

func checkPort(port int64) error {
	if port < 1 || port > 65535 {
		return errors.New("must be from 1 to 65535")
	}
	return nil
}

// checkMCPCeiling admits only catalog servers, and only required servers that
// are also allowed.
func checkMCPCeiling(p MCPPolicy) error {
	catalog := MCPServerIDs()
	known := func(id string) bool { return slices.Contains(catalog, id) }
	allowed := func(id string) bool { return slices.Contains(p.AllowedServers, id) }
	if !all(p.AllowedServers, known) || !all(p.RequiredServers, known) || !all(p.RequiredServers, allowed) {
		return errors.New("invalid operator MCP policy")
	}
	return nil
}

func all(values []string, keep func(string) bool) bool {
	return !slices.ContainsFunc(values, func(v string) bool { return !keep(v) })
}

// checkLength checks the length of value in characters, as Pydantic counts
// it.
func checkLength(value string, minimum, maximum int) error {
	n := utf8.RuneCountInString(value)
	if n < minimum || n > maximum {
		return errors.New("has a length outside the permitted range")
	}
	return nil
}

// isPythonSpace reports whether str.strip of Python removes r. Python also
// strips the separators U+001C to U+001F, which the IsSpace function of the
// unicode package does not include.
func isPythonSpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}
