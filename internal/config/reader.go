package config

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
)

// FieldError reports one member that breaks a rule. It holds the path of the
// member and the rule, never the value.
type FieldError struct {
	Path string
	Rule string
}

// ValidationError lists each member of a configuration that breaks a rule.
type ValidationError struct {
	Fields []FieldError
}

func (e *ValidationError) Error() string {
	var b strings.Builder
	b.WriteString("invalid configuration")
	for _, f := range e.Fields {
		b.WriteString("\n  ")
		b.WriteString(f.Path)
		b.WriteString(": ")
		b.WriteString(f.Rule)
	}
	return b.String()
}

// The rules that the member reader reports.
const (
	ruleRequired = "field required"
	ruleNull     = "must not be null"
	ruleString   = "must be a string"
	ruleInteger  = "must be an integer"
	ruleBoolean  = "must be a boolean"
	ruleArray    = "must be an array"
	ruleObject   = "must be an object"
	ruleUnknown  = "unknown field"
)

// report collects the field errors of one decode.
type report struct {
	fields []FieldError
}

func (r *report) fail(path, rule string) {
	r.fields = append(r.fields, FieldError{Path: path, Rule: rule})
}

func (r *report) err() error {
	if len(r.fields) == 0 {
		return nil
	}
	return &ValidationError{Fields: r.fields}
}

// object reads the members of one JSON object with the presence rules of the
// Python model: an absent member gets its default, only an optional member
// accepts null, and finish reports each member that no read used.
type object struct {
	path    string
	members map[string]any
	used    map[string]bool
	r       *report
}

func newObject(r *report, path string, members map[string]any) *object {
	return &object{path: path, members: members, used: map[string]bool{}, r: r}
}

func join(path, name string) string {
	if path == "" {
		return name
	}
	return path + "." + name
}

func (o *object) at(name string) string {
	return join(o.path, name)
}

func (o *object) fail(name, rule string) {
	o.r.fail(o.at(name), rule)
}

// take returns the value of a member and whether it is present.
func (o *object) take(name string) (any, bool) {
	o.used[name] = true
	v, ok := o.members[name]
	return v, ok
}

// value returns the value of a member that is not optional. ok is false when
// the member is absent or holds an error.
func (o *object) value(name string, required bool) (any, bool) {
	v, present := o.take(name)
	switch {
	case !present:
		if required {
			o.fail(name, ruleRequired)
		}
		return nil, false
	case v == nil:
		o.fail(name, ruleNull)
		return nil, false
	}
	return v, true
}

// optional returns the value of an optional member. ok is false when the
// member is absent or null.
func (o *object) optional(name string) (any, bool) {
	v, present := o.take(name)
	return v, present && v != nil
}

func (o *object) asString(name string, v any) (string, bool) {
	s, ok := v.(string)
	if !ok {
		o.fail(name, ruleString)
	}
	return s, ok
}

func (o *object) asInteger(name string, v any) (int64, bool) {
	n, ok := v.(int64)
	if !ok {
		o.fail(name, ruleInteger)
	}
	return n, ok
}

func (o *object) asStrings(name string, v any) ([]string, bool) {
	items, ok := v.([]any)
	if !ok {
		o.fail(name, ruleArray)
		return nil, false
	}
	out := make([]string, 0, len(items))
	valid := true
	for i, item := range items {
		s, isString := item.(string)
		if !isString {
			o.r.fail(join(o.at(name), strconv.Itoa(i)), ruleString)
			valid = false
		}
		out = append(out, s)
	}
	return out, valid
}

// str reads a string member with a default. ok is false when the member is
// absent or holds an error, so the caller checks only a present value.
func (o *object) str(name, def string, required bool) (string, bool) {
	v, ok := o.value(name, required)
	if !ok {
		return def, false
	}
	return o.asString(name, v)
}

func (o *object) optStr(name string) (*string, bool) {
	v, ok := o.optional(name)
	if !ok {
		return nil, false
	}
	s, ok := o.asString(name, v)
	if !ok {
		return nil, false
	}
	return &s, true
}

func (o *object) integer(name string, def int64) (int64, bool) {
	v, ok := o.value(name, false)
	if !ok {
		return def, false
	}
	return o.asInteger(name, v)
}

func (o *object) optInteger(name string) (*int64, bool) {
	v, ok := o.optional(name)
	if !ok {
		return nil, false
	}
	n, ok := o.asInteger(name, v)
	if !ok {
		return nil, false
	}
	return &n, true
}

func (o *object) boolean(name string, def bool) bool {
	v, ok := o.value(name, false)
	if !ok {
		return def
	}
	b, isBool := v.(bool)
	if !isBool {
		o.fail(name, ruleBoolean)
		return def
	}
	return b
}

// strings reads an array of strings that is not optional.
func (o *object) strings(name string) ([]string, bool) {
	v, ok := o.value(name, false)
	if !ok {
		return nil, false
	}
	return o.asStrings(name, v)
}

func (o *object) optStrings(name string) ([]string, bool) {
	v, ok := o.optional(name)
	if !ok {
		return nil, false
	}
	return o.asStrings(name, v)
}

// child returns the member as an object. ok is false when the member is
// absent or holds an error. A null member is an error unless nullable.
func (o *object) child(name string, required, nullable bool) (*object, bool) {
	var v any
	var ok bool
	if nullable {
		v, ok = o.optional(name)
	} else {
		v, ok = o.value(name, required)
	}
	if !ok {
		return nil, false
	}
	members, isObject := v.(map[string]any)
	if !isObject {
		o.fail(name, ruleObject)
		return nil, false
	}
	return newObject(o.r, o.at(name), members), true
}

// items returns the elements of an array member as objects. An element that
// is not an object is an error.
func (o *object) items(name string) []*object {
	v, ok := o.value(name, false)
	if !ok {
		return nil
	}
	elements, isArray := v.([]any)
	if !isArray {
		o.fail(name, ruleArray)
		return nil
	}
	out := make([]*object, 0, len(elements))
	for i, element := range elements {
		path := join(o.at(name), strconv.Itoa(i))
		members, isObject := element.(map[string]any)
		if !isObject {
			o.r.fail(path, ruleObject)
			continue
		}
		out = append(out, newObject(o.r, path, members))
	}
	return out
}

// finish reports each member that no read used, in name order. A name that
// is not a plain identifier is reported as unknownName, so an error never
// holds control characters or another arbitrary member name.
func (o *object) finish() {
	var unknown []string
	for name := range o.members {
		if !o.used[name] {
			unknown = append(unknown, name)
		}
	}
	slices.Sort(unknown)
	for _, name := range unknown {
		if !plainNamePattern.MatchString(name) {
			name = unknownName
		}
		o.fail(name, ruleUnknown)
	}
}

// unknownName replaces a member name that is not a plain identifier in an
// error.
const unknownName = "<member>"

// plainNamePattern matches the member names that an error can show.
var plainNamePattern = regexp.MustCompile(`\A[A-Za-z0-9_.-]{1,64}\z`)
