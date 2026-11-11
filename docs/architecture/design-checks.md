# Design-check tools

LilRAE has four existing design-check categories: compilation, structure, wiring, and acceptance.
They answer different questions.
None proves runtime containment or complete implementation correctness.
`.ground-control.yaml` does not configure a separate design-check workflow.

## The four design checks

Compilation finds Python syntax errors and creates bytecode.
The repository has no separate configured type checker.
The structural checks apply the existing architecture and participant dependency rules.
The wiring view shows observed imports, including imports that do not satisfy the target architecture.
[ADR-064](../adrs/adr-064-layered-architecture-and-code-conventions.md) distinguishes target rules from staged enrollment.

The [tool reference](../reference/design-check-tools.md#tool-contracts) lists executable owners and output contracts.

## The acceptance adapter

The acceptance adapter reports one observed test result.
An observed failing assertion can be a valid adapter result.
Adapter success therefore does not mean test success.
The [JSON reference](../reference/design-check-tools.md#the-acceptance-adapter) defines statuses and exit behavior.

## Run the checks

Behavior tests, including the acceptance adapter, run only in CI or an approved isolated VM.
The workstation supports source review and static checks.
The [contribution guide](../contributing-documentation.md#run-writing-checks) describes the documentation checks.
[CI verification](ci-verification.md) explains test selection and qualification boundaries.
