package architecture

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// The markers of the generated diagram block in a document.
const (
	diagramBegin = "<!-- Generated from architecture/model.yaml by archcheck diagram. Do not edit. -->"
	diagramEnd   = "<!-- End of the generated diagram. -->"
)

// Diagram checks the generated diagram block of the document doc against the
// model of the working tree that holds dir. With write, it replaces the block
// instead.
func Diagram(ctx context.Context, dir, doc string, write bool) (report Report, err error) {
	top, root, err := openRepository(ctx, dir)
	if err != nil {
		return Report{}, err
	}
	defer func() { err = errors.Join(err, closeRoot(root)) }()
	m, err := loadModel(root)
	if err != nil {
		return Report{}, err
	}
	if findings := m.validate(); len(findings) > 0 {
		return Report{Findings: findings}, nil
	}
	rel, err := treePath(top, doc)
	if err != nil {
		return Report{}, err
	}
	name := filepath.ToSlash(rel)
	data, err := root.ReadFile(rel)
	if err != nil {
		return Report{}, fmt.Errorf("read %s: %w", name, err)
	}
	before, rest, ok := bytes.Cut(data, []byte(diagramBegin))
	if !ok {
		return Report{}, fmt.Errorf("%s has no generated diagram block", name)
	}
	current, after, ok := bytes.Cut(rest, []byte(diagramEnd))
	if !ok {
		return Report{}, fmt.Errorf("%s has no end marker for the generated diagram", name)
	}
	want := "\n" + renderDiagram(m) + "\n"
	if string(current) == want {
		return Report{}, nil
	}
	if !write {
		return Report{Findings: []Finding{m.finding(RuleStaleDiagram, name, "the generated diagram differs from the model")}}, nil
	}
	info, err := root.Stat(rel)
	if err != nil {
		return Report{}, fmt.Errorf("read %s: %w", name, err)
	}
	updated := bytes.Join([][]byte{before, []byte(diagramBegin + want + diagramEnd), after}, nil)
	return Report{}, replaceFile(root, rel, updated, info.Mode().Perm())
}

// renderDiagram returns a Mermaid flowchart of the layers, the components, and
// their uses. Each name is a validated identifier, so the diagram holds no free
// text.
func renderDiagram(m *Model) string {
	var b strings.Builder
	b.WriteString("```mermaid\nflowchart TB\n")
	for _, l := range m.Layers {
		var members []string
		for i := range m.Components {
			if m.Components[i].Layer == l.Name {
				members = append(members, m.Components[i].Name)
			}
		}
		if len(members) == 0 {
			continue
		}
		fmt.Fprintf(&b, "    subgraph layer_%s[%s]\n", strings.ReplaceAll(l.Name, "-", "_"), l.Name)
		for _, name := range members {
			fmt.Fprintf(&b, "        %s[%s]\n", nodeID(name), name)
		}
		b.WriteString("    end\n")
	}
	for i := range m.Components {
		c := &m.Components[i]
		for _, used := range c.Uses {
			fmt.Fprintf(&b, "    %s --> %s\n", nodeID(c.Name), nodeID(used))
		}
		for _, used := range c.TestUses {
			fmt.Fprintf(&b, "    %s -. test .-> %s\n", nodeID(c.Name), nodeID(used))
		}
	}
	b.WriteString("```")
	return b.String()
}

// nodeID returns the Mermaid node identifier of a component name. The prefix
// keeps a name such as "end" from becoming a Mermaid keyword.
func nodeID(name string) string {
	return "component_" + strings.ReplaceAll(name, "-", "_")
}

// replaceFile replaces the file name in root atomically (ADR-065): it writes
// data to a new temporary file in the same directory, syncs it, and renames it
// over name. After a failure, name is unchanged and the temporary file is gone.
func replaceFile(root *os.Root, name string, data []byte, perm os.FileMode) error {
	temp := fmt.Sprintf("%s.%d.tmp", name, os.Getpid())
	f, err := root.OpenFile(temp, os.O_WRONLY|os.O_CREATE|os.O_EXCL, perm)
	if err != nil {
		return fmt.Errorf("create %s: %w", temp, err)
	}
	if _, err := f.Write(data); err != nil {
		return errors.Join(fmt.Errorf("write %s: %w", temp, err), f.Close(), removeTemp(root, temp))
	}
	if err := f.Sync(); err != nil {
		return errors.Join(fmt.Errorf("sync %s: %w", temp, err), f.Close(), removeTemp(root, temp))
	}
	if err := f.Close(); err != nil {
		return errors.Join(fmt.Errorf("close %s: %w", temp, err), removeTemp(root, temp))
	}
	if err := root.Rename(temp, name); err != nil {
		return errors.Join(fmt.Errorf("replace %s: %w", name, err), removeTemp(root, temp))
	}
	return nil
}

// removeTemp removes the temporary file of a failed replacement.
func removeTemp(root *os.Root, temp string) error {
	if err := root.Remove(temp); err != nil {
		return fmt.Errorf("remove %s: %w", temp, err)
	}
	return nil
}
