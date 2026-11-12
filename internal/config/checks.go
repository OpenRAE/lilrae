package config

import (
	"errors"
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
	claudeModelPattern        = regexp.MustCompile(`\Aclaude-(?:[a-z0-9-]+[-@][0-9]{8}|(?:sonnet|opus|haiku)-[1-9][0-9]*)\z`)
	codexModelPattern         = regexp.MustCompile(`\A(?:codex-[a-z0-9._-]+|gpt-[a-z0-9._-]+|o[0-9][a-z0-9._-]*)-[0-9]{4}-[0-9]{2}-[0-9]{2}\z`)
)

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

func checkGrantVariable(value string) error {
	if err := checkLength(value, 1, 128); err != nil {
		return err
	}
	if !environmentNamePattern.MatchString(value) {
		return errors.New("environment grant variable is invalid")
	}
	return nil
}

func checkKind(kind string, kinds []string) error {
	if !slices.Contains(kinds, kind) {
		return errors.New("unknown credential source kind")
	}
	return nil
}

// checkSourceVariable checks the variable locator of a source of a known
// kind.
func checkSourceVariable(kind, variable string) error {
	if err := checkLength(variable, 1, 128); err != nil {
		return err
	}
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
	switch {
	case clean == "":
		return "", errors.New("scenario root must not be empty")
	case strings.ContainsRune(clean, 0):
		return "", errors.New("scenario root must not contain a NUL byte")
	case strings.HasPrefix(clean, "/") || slices.Contains(strings.Split(clean, "/"), ".."):
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

// immutableModelPattern returns the pattern of the immutable model names of
// an installed provider, which is claude or codex.
func immutableModelPattern(provider string) *regexp.Regexp {
	if provider == "claude" {
		return claudeModelPattern
	}
	return codexModelPattern
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
// strips the separators U+001C to U+001F, which unicode.IsSpace does not
// include.
func isPythonSpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}
