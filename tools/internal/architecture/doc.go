// Package architecture checks a repository and its design notes against the
// architecture model of ADR-065.
//
// The model (architecture/model.yaml) names the layers, the components with
// their packages, the components and modules that each component can use,
// the public packages, the vendored source, and a fix-it message for each
// rule. The checker reads the imports of each tracked first-party Go file with
// the Go parser, resolves each import, and reports each import that the model
// does not permit. It runs no project code.
//
// A design note (docs/architecture/issue-<number>-<topic>-design.md) starts
// with a design record in YAML front matter. The record names the new,
// changed, and removed packages, their imports, and the changed parts of the
// model. The design check compares the record with the model before the code
// exists, and the pull request check compares it with the code.
package architecture
