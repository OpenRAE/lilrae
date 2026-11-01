# Go Architecture

`architecture/model.yaml` is the architecture model of
[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md). It
gives the layers, the components, the packages of each component, and the
components and modules that each component can use. The
[#1583 design](issue-1583-architecture-model-design.md) gives the schema and the
rules.

`archcheck check` checks the repository against the model. The diagram shows
the layers, the components, and the uses that the model permits. A dashed arrow
shows a use that the model permits only for test files.
`archcheck diagram -write` makes the diagram from the model, and CI fails when
the diagram differs from the model. Do not edit the diagram by hand.

<!-- Generated from architecture/model.yaml by archcheck diagram. Do not edit. -->
```mermaid
flowchart TB
    subgraph layer_tools[tools]
        component_regressioncheck_command[regressioncheck-command]
        component_mutationcheck_command[mutationcheck-command]
        component_archcheck_command[archcheck-command]
        component_regression_check[regression-check]
        component_mutation_check[mutation-check]
        component_architecture_check[architecture-check]
        component_check_command[check-command]
        component_go_layout[go-layout]
        component_git[git]
        component_git_test_support[git-test-support]
        component_gate_fixtures[gate-fixtures]
    end
    subgraph layer_build[build]
        component_caddy_build[caddy-build]
    end
    component_regressioncheck_command --> component_regression_check
    component_regressioncheck_command --> component_check_command
    component_regressioncheck_command -. test .-> component_git_test_support
    component_mutationcheck_command --> component_mutation_check
    component_mutationcheck_command --> component_check_command
    component_mutationcheck_command -. test .-> component_git_test_support
    component_archcheck_command --> component_architecture_check
    component_archcheck_command --> component_check_command
    component_archcheck_command -. test .-> component_git_test_support
    component_regression_check --> component_git
    component_regression_check --> component_go_layout
    component_regression_check -. test .-> component_git_test_support
    component_mutation_check --> component_git
    component_mutation_check --> component_go_layout
    component_mutation_check -. test .-> component_git_test_support
    component_architecture_check --> component_git
    component_architecture_check --> component_go_layout
    component_architecture_check -. test .-> component_git_test_support
    component_git -. test .-> component_git_test_support
    component_git_test_support -. test .-> component_git
```
<!-- End of the generated diagram. -->
