package architecture

import (
	"bytes"
	"errors"
	"fmt"
	"io"

	"go.yaml.in/yaml/v3"
)

// maxInput bounds the size of a model or a design record.
const maxInput = 1 << 20

// decodeStrict decodes one YAML document into v and returns its node tree. It
// rejects input over maxInput, unknown fields, duplicate keys, more than one
// document, aliases, anchors, and custom tags.
func decodeStrict(data []byte, v any) (*yaml.Node, error) {
	if len(data) > maxInput {
		return nil, fmt.Errorf("the input is larger than %d bytes", maxInput)
	}
	var root yaml.Node
	dec := yaml.NewDecoder(bytes.NewReader(data))
	if err := dec.Decode(&root); err != nil {
		return nil, fmt.Errorf("decode the YAML document: %w", err)
	}
	var next yaml.Node
	if err := dec.Decode(&next); !errors.Is(err, io.EOF) {
		return nil, errors.New("the input holds more than one YAML document")
	}
	if err := plainNodes(&root); err != nil {
		return nil, err
	}
	strict := yaml.NewDecoder(bytes.NewReader(data))
	strict.KnownFields(true)
	if err := strict.Decode(v); err != nil {
		return nil, fmt.Errorf("decode the YAML document: %w", err)
	}
	return &root, nil
}

// plainNodes rejects aliases, anchors, and custom tags in a node tree.
func plainNodes(n *yaml.Node) error {
	if n.Kind == yaml.AliasNode || n.Anchor != "" {
		return fmt.Errorf("line %d: YAML aliases and anchors are not supported", n.Line)
	}
	if !plainTag(n.Tag) {
		return fmt.Errorf("line %d: the YAML tag %q is not supported", n.Line, n.Tag)
	}
	for _, child := range n.Content {
		if err := plainNodes(child); err != nil {
			return err
		}
	}
	return nil
}

// plainTag reports whether tag is a tag of plain data. Other tags select
// custom types.
func plainTag(tag string) bool {
	switch tag {
	case "", "!!map", "!!seq", "!!str", "!!int", "!!bool", "!!null":
		return true
	}
	return false
}
