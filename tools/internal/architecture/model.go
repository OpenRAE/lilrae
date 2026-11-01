package architecture

import (
	"fmt"
	"maps"
	"path"
	"regexp"
	"slices"
	"strings"

	"go.yaml.in/yaml/v3"
	"golang.org/x/mod/module"
)

// ModelPath is the path of the model in a repository.
const ModelPath = "architecture/model.yaml"

// The rules of the checker. The model gives the fix-it message of each.
const (
	RuleUnassignedPackage   = "unassigned-package"
	RuleStalePackage        = "stale-package"
	RuleForbiddenImport     = "forbidden-import"
	RuleForbiddenModule     = "forbidden-module"
	RuleUnresolvedImport    = "unresolved-import"
	RuleUndeclaredPublic    = "undeclared-public-package"
	RuleLocalReplacement    = "undeclared-replacement"
	RuleInvalidModel        = "invalid-model"
	RuleMissingDesign       = "missing-design"
	RuleInvalidDesign       = "invalid-design"
	RuleDesignPackageAbsent = "design-package-missing"
	RuleDesignImportsDiffer = "design-imports-differ"
	RuleDesignForbidden     = "design-forbidden"
	RuleDesignModelChanges  = "design-model-changes-differ"
	RuleStaleDiagram        = "stale-diagram"
)

// rules returns each rule of the checker.
func rules() []string {
	return []string{
		RuleUnassignedPackage, RuleStalePackage, RuleForbiddenImport, RuleForbiddenModule,
		RuleUnresolvedImport, RuleUndeclaredPublic, RuleLocalReplacement, RuleInvalidModel, RuleMissingDesign,
		RuleInvalidDesign, RuleDesignPackageAbsent, RuleDesignImportsDiffer, RuleDesignForbidden,
		RuleDesignModelChanges, RuleStaleDiagram,
	}
}

var namePattern = regexp.MustCompile(`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`)

// Model is the architecture model of a repository.
type Model struct {
	Version    int               `yaml:"version"`
	Layers     []Layer           `yaml:"layers"`
	Components []Component       `yaml:"components"`
	Public     []string          `yaml:"public"`
	Vendored   []string          `yaml:"vendored"`
	Rules      map[string]string `yaml:"rules"`

	// lines holds the line of each top-level field.
	lines map[string]int
	// layerLines and componentLines hold the line of each layer and
	// component, by index.
	layerLines, componentLines []int
}

// Layer is a layer of the model.
type Layer struct {
	Name        string   `yaml:"name"`
	Description string   `yaml:"description"`
	MayUse      []string `yaml:"may_use"`
}

// Component is a component of the model.
type Component struct {
	Name           string   `yaml:"name"`
	Layer          string   `yaml:"layer"`
	Responsibility string   `yaml:"responsibility"`
	Packages       []string `yaml:"packages"`
	Uses           []string `yaml:"uses"`
	Modules        []string `yaml:"modules"`
	TestUses       []string `yaml:"test_uses"`
	TestModules    []string `yaml:"test_modules"`
}

// parseModel decodes a model. An empty input is the empty model, which a
// revision without a model has.
func parseModel(data []byte) (*Model, error) {
	var m Model
	if len(data) == 0 {
		return &m, nil
	}
	root, err := decodeStrict(data, &m)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", ModelPath, err)
	}
	if m.Version != 1 {
		return nil, fmt.Errorf("%s: the model version must be 1", ModelPath)
	}
	m.recordLines(root)
	return &m, nil
}

// recordLines records the line of each top-level field, layer, and component.
// The root node holds the decoded document, whose content is a mapping.
func (m *Model) recordLines(root *yaml.Node) {
	m.lines = map[string]int{}
	for pair := range slices.Chunk(root.Content[0].Content, 2) {
		key := pair[0].Value
		m.lines[key] = pair[0].Line
		switch key {
		case "layers":
			m.layerLines = itemLines(pair[1])
		case "components":
			m.componentLines = itemLines(pair[1])
		}
	}
}

// itemLines returns the line of each item of a sequence node.
func itemLines(list *yaml.Node) []int {
	lines := make([]int, len(list.Content))
	for i, item := range list.Content {
		lines[i] = item.Line
	}
	return lines
}

// location returns the model location of a top-level field.
func (m *Model) location(field string) string {
	return lineLocation(m.lines[field])
}

// layerLocation and componentLocation return the model location of a layer
// and of a component, by index. The decoder gives one line for each item.
func (m *Model) layerLocation(i int) string     { return lineLocation(m.layerLines[i]) }
func (m *Model) componentLocation(i int) string { return lineLocation(m.componentLines[i]) }

func lineLocation(line int) string {
	if line > 0 {
		return fmt.Sprintf("%s:%d", ModelPath, line)
	}
	return ModelPath
}

// component returns the component with name, or nil.
func (m *Model) component(name string) *Component {
	for i := range m.Components {
		if m.Components[i].Name == name {
			return &m.Components[i]
		}
	}
	return nil
}

// owner returns the component that holds the package directory dir, or nil.
func (m *Model) owner(dir string) *Component {
	for i := range m.Components {
		if slices.Contains(m.Components[i].Packages, dir) {
			return &m.Components[i]
		}
	}
	return nil
}

// fixIt returns the fix-it message of rule.
func (m *Model) fixIt(rule string) string {
	if message := strings.TrimSpace(m.Rules[rule]); message != "" {
		return message
	}
	return "The model gives no fix-it message for this rule."
}

// finding returns a finding of rule with the fix-it message of the model.
func (m *Model) finding(rule, location, message string) Finding {
	return Finding{Rule: rule, Location: location, Message: message, FixIt: m.fixIt(rule)}
}

// validate returns the semantic problems of the model.
func (m *Model) validate() []Finding {
	findings := m.validateLayers()
	layers := map[string]Layer{}
	for _, l := range m.Layers {
		layers[l.Name] = l
	}
	owners := map[string]string{}
	for i := range m.Components {
		findings = append(findings, m.validateComponent(i, layers, owners)...)
		findings = append(findings, m.validateDependencies(i, layers)...)
	}
	findings = append(findings, m.validatePublic()...)
	findings = append(findings, m.validateVendored()...)
	return append(findings, m.validateRules()...)
}

// problem returns an invalid-model finding at a model location.
func (m *Model) problem(location, format string, args ...any) Finding {
	return m.finding(RuleInvalidModel, location, fmt.Sprintf(format, args...))
}

// validateLayers returns the problems of the layers.
func (m *Model) validateLayers() []Finding {
	var findings []Finding
	names := map[string]bool{}
	for i, l := range m.Layers {
		if !namePattern.MatchString(l.Name) {
			findings = append(findings, m.problem(m.layerLocation(i), "the layer name %q is not lower-case words joined by hyphens", l.Name))
		}
		if names[l.Name] {
			findings = append(findings, m.problem(m.layerLocation(i), "the layer %q is defined twice", l.Name))
		}
		names[l.Name] = true
	}
	for i, l := range m.Layers {
		for _, used := range l.MayUse {
			if !names[used] {
				findings = append(findings, m.problem(m.layerLocation(i), "the layer %q may use the unknown layer %q", l.Name, used))
			}
		}
	}
	return findings
}

// validateComponent returns the problems of the fields and packages of the
// component at index i. owners maps each package seen so far to its component.
func (m *Model) validateComponent(i int, layers map[string]Layer, owners map[string]string) []Finding {
	var findings []Finding
	c := &m.Components[i]
	key := m.componentLocation(i)
	if !namePattern.MatchString(c.Name) {
		findings = append(findings, m.problem(key, "the component name %q is not lower-case words joined by hyphens", c.Name))
	}
	if m.countComponents(c.Name) > 1 {
		findings = append(findings, m.problem(key, "the component %q is defined twice", c.Name))
	}
	if _, ok := layers[c.Layer]; !ok {
		findings = append(findings, m.problem(key, "the component %q has the unknown layer %q", c.Name, c.Layer))
	}
	if strings.TrimSpace(c.Responsibility) == "" {
		findings = append(findings, m.problem(key, "the component %q has no responsibility", c.Name))
	}
	if len(c.Packages) == 0 {
		findings = append(findings, m.problem(key, "the component %q has no package", c.Name))
	}
	for _, p := range c.Packages {
		if !validPath(p) {
			findings = append(findings, m.problem(key, "the package %q of %q is not a clean relative path", p, c.Name))
		}
		if other, dup := owners[p]; dup {
			findings = append(findings, m.problem(key, "the package %q is in %q and in %q", p, other, c.Name))
		}
		owners[p] = c.Name
	}
	return findings
}

// validateDependencies returns the problems of the uses and modules of the
// component at index i.
func (m *Model) validateDependencies(i int, layers map[string]Layer) []Finding {
	var findings []Finding
	c := &m.Components[i]
	key := m.componentLocation(i)
	layer, layerKnown := layers[c.Layer]
	for _, used := range slices.Concat(c.Uses, c.TestUses) {
		findings = append(findings, m.validateUse(c, key, layer, layerKnown, used)...)
	}
	for _, problem := range listProblems(c.Uses, c.TestUses) {
		findings = append(findings, m.problem(key, "the uses of %q %s", c.Name, problem))
	}
	for _, mod := range slices.Concat(c.Modules, c.TestModules) {
		if module.CheckPath(mod) != nil {
			findings = append(findings, m.problem(key, "the module %q of %q is not a valid module path", mod, c.Name))
		}
	}
	for _, problem := range listProblems(c.Modules, c.TestModules) {
		findings = append(findings, m.problem(key, "the modules of %q %s", c.Name, problem))
	}
	return findings
}

// validateUse returns the problems of a use of c, at the model location key.
// layerKnown reports that the layer of c exists.
func (m *Model) validateUse(c *Component, key string, layer Layer, layerKnown bool, used string) []Finding {
	if used == c.Name {
		return []Finding{m.problem(key, "the component %q uses itself", c.Name)}
	}
	target := m.component(used)
	if target == nil {
		return []Finding{m.problem(key, "the component %q uses the unknown component %q", c.Name, used)}
	}
	if layerKnown && !slices.Contains(layer.MayUse, target.Layer) {
		return []Finding{m.problem(key, "the layer %q of %q may not use the layer %q of %q", c.Layer, c.Name, target.Layer, used)}
	}
	return nil
}

// validatePublic returns the problems of the public packages.
func (m *Model) validatePublic() []Finding {
	var findings []Finding
	key := m.location("public")
	for _, p := range m.Public {
		if m.owner(p) == nil {
			findings = append(findings, m.problem(key, "the public package %q is in no component", p))
		}
		if internalPath(p) {
			findings = append(findings, m.problem(key, "the public package %q is under internal/", p))
		}
	}
	for _, problem := range listProblems(m.Public, nil) {
		findings = append(findings, m.problem(key, "the public packages %s", problem))
	}
	return findings
}

// validateVendored returns the problems of the vendored directories.
func (m *Model) validateVendored() []Finding {
	var findings []Finding
	for _, v := range m.Vendored {
		if !validPath(v) || v == "." {
			findings = append(findings, m.problem(m.location("vendored"), "the vendored directory %q is not a clean relative path", v))
		}
		for i := range m.Components {
			for _, p := range m.Components[i].Packages {
				if within(p, v) {
					findings = append(findings, m.problem(m.componentLocation(i),
						"the package %q of %q is in the vendored directory %q", p, m.Components[i].Name, v))
				}
			}
		}
	}
	for _, problem := range listProblems(m.Vendored, nil) {
		findings = append(findings, m.problem(m.location("vendored"), "the vendored directories %s", problem))
	}
	return findings
}

// validateRules returns the problems of the fix-it messages.
func (m *Model) validateRules() []Finding {
	var findings []Finding
	for _, rule := range rules() {
		if strings.TrimSpace(m.Rules[rule]) == "" {
			findings = append(findings, m.problem(m.location("rules"), "the rule %q has no fix-it message", rule))
		}
	}
	unknown := slices.Sorted(maps.Keys(m.Rules))
	for _, rule := range unknown {
		if !slices.Contains(rules(), rule) {
			findings = append(findings, m.problem(m.location("rules"), "the rule %q is unknown", rule))
		}
	}
	return findings
}

func (m *Model) countComponents(name string) int {
	n := 0
	for i := range m.Components {
		if m.Components[i].Name == name {
			n++
		}
	}
	return n
}

// listProblems returns the problems of a list and an extra list: an entry
// that appears twice, or in both lists.
func listProblems(list, extra []string) []string {
	var problems []string
	seen := map[string]bool{}
	for _, entry := range slices.Concat(list, extra) {
		if seen[entry] {
			problems = append(problems, fmt.Sprintf("list %q twice", entry))
		}
		seen[entry] = true
	}
	return problems
}

// validPath reports whether p is a clean, relative, slash-separated path that
// stays in the repository.
func validPath(p string) bool {
	return p != "" && path.Clean(p) == p && !path.IsAbs(p) && p != ".." && !strings.HasPrefix(p, "../") && !strings.Contains(p, `\`)
}

// within reports whether path p is dir or below dir.
func within(p, dir string) bool {
	return dir == "." || p == dir || strings.HasPrefix(p, dir+"/")
}

// internalPath reports whether a package path has an internal element, so the
// go command limits its importers.
func internalPath(p string) bool {
	return slices.Contains(strings.Split(p, "/"), "internal")
}
