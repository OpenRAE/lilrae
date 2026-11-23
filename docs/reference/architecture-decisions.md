# Architecture decision format

[ADR-000](../adrs/adr-000-use-adrs.md) defines decision governance.
This Reference describes the existing record structure.
The [decision index](../adrs/README.md) lists recorded statuses and dates.

## Template

```markdown
# ADR-NNN: [Title]

## Status

[proposed | accepted | deprecated | superseded by ADR-XXX]

## Date

YYYY-MM-DD

## Context

[The problem and the reasons for a decision.]

## Decision

[The selected change and its reasons.]

## Consequences

### Positive

- [A benefit.]

### Negative

- [A cost.]

### Risks

- [A remaining risk.]
```

The template lists common status forms.
ADR-000 also permits rejection of a proposed decision.
Some records state partial supersession or include amendments.
Their exact Status sections remain authoritative for the recorded decision.

## Existing links

An editorial rewrite keeps record numbers, dates, status, reasons, and amendment links.
A changed implementation does not silently change an accepted decision.
A successor record states what it replaces.
Old useful heading links remain available when task or lookup material moves.
