# Participant action and control architecture assessment

Date: 2026-10-31.
Status: research for discussion. No implementation architecture is accepted here.
Scope: LilRAE #1418 and the surrounding RAE language, participant, action, control, realization, and evidence boundaries.

The subsequent [enforcement design](participant-action-enforcement.md) builds on this assessment.
It defines the executable model and implementation for the same delivery PR.
This assessment retains the research findings and their original evidence limits.

## Result and limits

The participant-control programme has a coherent purpose and substantial existing research.
This assessment does not justify dismissing that programme as a rabbit hole.
It does identify concrete ways that local implementation can drift from its goals.
The initial #1418 plan made several choices too early.

The strongest immediate concern is composition.
The released invocation tool port refuses configurations with participant-crossing policy installed.
Separate support for tools and participant control therefore does not establish their joint support.
The successful tool-history probe does not settle that architecture question.

The authoring and evidence boundaries also need correction in the local plan.
RAE already rejects mandatory installation recipes and unrequested experimental collection.
Tool integration must preserve those decisions.

This is a targeted architecture assessment, not a systematic literature review or security certification.
External documentation, original papers, and selected implementation code and tests were inspected.
External implementations were not installed, executed, or independently security-audited.
Recommendations below are engineering judgments, not experimental results.

## Evidence cut and method

RAE was inspected at released tags `v10.1.0` and `v10.2.0`.
LilRAE was inspected from `9ae37a5f` on `1418-participant-tool-runtime`.
The RAE checkout was read only; uncommitted work was not used as released evidence.
Historical research status tables were distinguished from current requirement files.
For example, SEM-235, API-424, RUN-320, and ASR-538 are ACTIVE at the assessed release.
ASR-537 remains DRAFT.
Those statuses describe bounded requirement completion, not every native backend or feature combination.

Existing research was read before extending the external comparison.
It includes participant identity, backend contracts, information flow, modular control, mixed backends, language extensibility, and language evaluation.
The external sources below are primary publications or official project sources.
Their use here does not select a new service, dependency, or deployment topology.

## Fundamental goals already established

| Goal | Existing authority | Consequence |
| --- | --- | --- |
| Describe intent at the author's chosen abstraction | [Language design intent][intent]; ADR-020/109 | A complete abstract model needs no machine, harness, process, or tool inventory. |
| Delegate unspecified realization choices | [Language design research][language] | An exact execution binding can be resolved by the backend at admission. It need not become mandatory author detail. |
| Preserve participant identity across implementations | [ADR-109][identity]; ADR-022 | Role, account, caller, controller, harness, participant, and episode remain distinct. |
| Govern actions and information under selected profiles | [ADR-085][boundary]; [ADR-108][modular] | Existing owners compose admission, projection, intervention, control, and effects. |
| Support different realizations honestly | [Mixed-backend research][mixed]; SEM-234 | A shared interface does not establish simulation/emulation equivalence or joint capability support. |
| Support bounded, inspectable research claims | ASR-536/537/538; [current support][support] | Contract tests, native realization, conformance, and experimental results are different claims. |
| Separate experimental evidence from operational state | [Design intent][intent]; ADR-064/066 | Runtime history does not automatically authorize research collection, retention, or export. |
| Keep the language usable and reviewable | [Language evaluation programme][evaluation] | Parser acceptance and formal definitions do not establish author productivity or comprehension. |

The identity boundary is already an accepted decision.
Authors designate the autonomous subject and its identity.
A composite harness, model, and tool set may constitute one participant.
Neither every tool nor every process becomes another participant automatically.
A human can direct a participant without being that participant.
Human study subjects are also distinct from SDL participants.

The global purpose is broader than recording MCP calls.
It is to preserve authored meaning, authority, observations, and justified evidence through supported realizations.
MCP is one realization interface within that model.

## Existing work to retain

The participant identity research separates identity, affiliation, role, objective ownership, and assignment.
ADR-109 corrected several findings from its earlier audit.
Those historical findings must not be reported as current defects without rechecking them.

The backend-contract research already compares Gymnasium, PettingZoo, OpenSpiel, OpenC2, CACAO, HLA, FMI, YANG, Vulkan, XACML, and OGC.
It separates action/observation interfaces, capability negotiation, command semantics, and retrieval.
Capability support never supplies action authority.

The information-flow and modular-control work establishes one semantic boundary over existing typed carriers.
That does not require one gateway, transport, service, message, history, or policy engine.
Facts, constraints, advice, and effect requests keep different meanings.
A monitor score is not permission; a replacement action requires fresh admission.

Mixed-backend research separates allocation, realization responsibility, participant control, time, mapping loss, and observation.
HLA ownership and message routing do not authorize participant actions.
The runtime-control-plane design separately distinguishes ephemeral embedding, local durability, and served operation through P0/P1/P2 profiles.
A local IPC choice cannot define every deployment topology.

Some documentation pointers need care during authority discovery.
The inspected unqualified LilRAE #6 pointer resolves to an old Terraform pull request.
It cannot establish current acceptance of an execution-compartment design.
Resolve architecture authority by exact repository and revision, rather than assuming old issue references still identify the intended work.

## External patterns and their limits

| Reference | Pattern established by the source | Application and boundary for RAE |
| --- | --- | --- |
| [Kubernetes authorization][kubernetes] and [admission][kube-admission] | Identity, authorization, and admission are different stages. Admission has explicit failure and side-effect rules. | Keep the authority chain explicit. Object admission is not a general native-effect transaction or participant model. |
| [Envoy external authorization][envoy] and [OPA][opa] | Enforcement can consult a separate decision service. Later route changes can invalidate earlier authorization. | Separate policy ownership from placement. Bind the final request and destination; an early permit cannot cover arbitrary later changes. |
| [Temporal activity execution][temporal] | Work has identity, lifecycle, external completion, cancellation, and retry policy. | Separate dispatch, completion, and uncertainty. Workflow nesting is not a universal participant model; native effects may be unsafe to retry. |
| [ROS 2 actions][ros] | Goal acceptance, execution, feedback, cancellation, and results have distinct states. | Useful asynchronous action precedent. Cancellation acceptance is not proof of cessation or authorization. |
| [SPIFFE][spiffe] | Workloads authenticate using short-lived identity documents across heterogeneous environments. | Workload identity can support a trust boundary. It does not itself identify an authored participant, controller, or permitted action. |
| [Inspect approval][inspect-approval] and [agent bridge][inspect-bridge] | External agents can use approved proposals, exact execution grants, and separate tool events. Unsupported approval paths are refused. | A close implementation precedent. Its evaluation lifecycle and exceptions do not constitute a portable participant-control standard. |
| [ControlArena][controlarena] | Policies and monitors compose into experimental control protocols. | Selected machinery may be reusable. Its task/trajectory model does not establish RAE authority or backend equivalence. |
| [OpenC2][openc2] and [CACAO 2.0][cacao] | Command meaning is separate from transfer protocols. CACAO includes manual and automated processing. | Humans and automation need not occupy separate semantic worlds. Neither standard supplies the whole RAE participant model. |
| [PettingZoo][pettingzoo] | Sequential and simultaneous interfaces have explicit conversion restrictions. | Execution order is semantic; wrappers must not silently change who can observe or act when. |
| [NIST UCEF][ucef] and the existing HLA review | Explicit adapters integrate simulations, emulators, and hardware. | Transport interoperability does not establish authority, observation equivalence, or empirical transfer. |
| [CUE][cue], [DSL development research][dsl], and [Cognitive Dimensions][cognitive] | Constraints refine independently. Language design must consider domain tasks, dependencies, and premature commitment. | Preserve author choice and abstraction. Assess effort and reviewability, rather than treating more fields as better language design. |
| [RFC 6709][extensions] | Changes to architectural assumptions and security models need deeper review than ordinary extensions. | Mandatory session state and cross-protocol dependencies can be consequential even when request syntax remains compatible. |

No inspected system solves the entire RAE problem.
Compare responsibilities, failure models, and actual evidence rather than product feature counts.

### Close implementation comparison

Inspect source was inspected at `3952947fe19838d23d15146e81b71049142b68f4`.
Its [host-tool implementation][inspect-code] consumes an execution grant for the exact server, tool, and arguments.
Its [tests][inspect-tests] cover forged calls, repeated execution, changed arguments, key order, and modified proposals.
It records execution separately from the model proposal.
The [retained design][inspect-design] also documents corrections and remaining limits.

There are important exceptions.
Provider-executed remote MCP calls cannot be approved locally and are refused while approval policy is active.
An explicitly exempt server gives up proposal correspondence.
That is a disclosed loss of a guarantee, not an equivalent implementation.
These details are more useful than simply citing tool approval as a feature.

ControlArena source was inspected at `ae0b6fa78ace5a097536eb3464ab5a089740b53e`.
Its [defer-to-trusted implementation][controlarena-code] proposes, monitors, and sometimes substitutes an action.
It retains the proposal, assessment, and substituted response for evaluation.
This supplies useful experimental machinery.
It does not establish that a substitute satisfies a separate action or information-flow policy.
RAE's fresh-admission requirement remains relevant.

### Research artifacts are not production references

Existing modular-control research already considers CaMeL, Fides, dynamic IFC, shields, edit automata, and AI control protocols.
Their maturity must remain explicit.
[CaMeL's repository][camel-code] describes an unsupported research artifact that may contain security bugs.
[Fides' repository][fides-code] provides a tutorial notebook accompanying a formal-model paper.
Neither is established here as a production security component suitable for adoption.

[AI Control][ai-control] studies intentional subversion and limited trusted labour.
[CaMeL][camel-paper] separates trusted control from untrusted data through capabilities.
[Fides][fides-paper] studies confidentiality, integrity, and planner expressiveness.
Their results do not transfer automatically to arbitrary shells, persistent sessions, or mixed native backends.

## Drift assessment beyond #1418

| Concern | Evidence and classification | Consequence |
| --- | --- | --- |
| Harness lifecycle becomes participant identity | A risk in the initial local plan; generalizing it conflicts with ADR-109. | Keep autonomous invocation as one execution arrangement. Do not invent autonomous wrappers for humans merely to fit an API. |
| Tool name becomes semantic action | A static mapping is insufficient for tools accepting different shell commands, API endpoints, methods, or targets. | Define the action abstraction and trusted mapping. A name cannot prove applicability, effects, or observation equivalence. |
| Features fail to compose | Released tool admission refuses crossing policy, resource-governed v3 policy, and shared-time-bound tools. Current support also refuses reusable control with mixed runtime. | Select required combinations from real tasks. Sound refusal does not deliver the combination, and separate passing features are insufficient. |
| Installation detail becomes author obligation | Existing design-intent work identifies this historical failure mode. Universal authored tool inventories could repeat it. | Resolve unconstrained detail in backend/apparatus admission. Keep explicit author constraints binding. |
| Runtime history implies archival | The initial local plan did not distinguish operational state from requested research retention. | Determine collection, retention, and export independently through existing owners. |
| Admission is mistaken for containment | Proposed ADR-057 and current launchers distinguish supervision from isolation. | Private sockets and environment credentials do not contain hostile code with the same host authority. |
| Research apparatus becomes a mandatory product platform | A risk, not an established repository-wide defect. Accepted designs explicitly allow optional profiles. | Keep advanced mechanisms selectable. Simple supported scenarios need a short authoring and execution path. |
| Contract completeness replaces user evidence | The inspected language-adequacy and accessibility bundles remain `not_started` and `untested`. | Do not claim usability from schemas, proofs, or tests. The existing user-study programme remains separate. |
| Citations replace integration evidence | Existing RAE documents generally disclose the limits correctly. The local tool-history probe had a much narrower scope. | Compare actual boundaries and counterexamples, rather than relying on papers or dependency versions alone. |

This supports a bounded conclusion.
There are real composition gaps and identifiable drift risks across several areas.
It does not establish that every advanced profile is unnecessary or that the whole architecture needs replacement.
The programme needs integration priorities driven by user and research tasks.

## Blast radius

| Area | Decisions that can propagate beyond this issue |
| --- | --- |
| SDL and tooling | Participant/action meaning, author obligations, optional profiles, schemas, diagnostics, and migration. |
| Runtime and stores | Authority cuts, dispatch grants, generations, recovery, histories, and P0/P1/P2 guarantees. |
| Backend contracts | Action/target mappings, support strength, capability claims, implementation identity, and conformance. |
| LilRAE entry paths | Direct harnesses, managed agents, host SSH, browser MCP, persistent sessions, and operational clients. |
| Other backends and adapters | Human, scripted, simulated, emulated, and mixed realizations need compatible meaning without identical internal topology. |
| Packs and study assembly | Participant profiles, installation choices, configuration, objectives, and trial allocation. |
| Security | Credential possession, revocation, destination binding, bypass paths, disclosure, and host integrity. |
| Evidence and research | Operational state, requested capture, retention, archive visibility, comparison, and claim limits. |
| Compatibility and operations | Dependency upgrades, offline use, deployment burden, availability, latency, and recovery procedures. |

A local socket may ultimately be a small backend detail.
Making its lifecycle, credential model, or capture policy universal has this broader impact.
Determine ownership and guarantees before selecting transport.

## Alternatives for discussion

| Candidate | Potential value | Main unresolved question |
| --- | --- | --- |
| Thin adapter for the existing autonomous port | A small implementation for a bounded subset. | Is that subset useful, and are its unsupported combinations acceptable? It cannot close a broader contract by omission. |
| Compose through existing participant-control authorities | Common meaning across controllers and realizations, with multiple adapters and transports. | Which upstream lifecycle and profile combinations need integration? Avoid another universal request model. |
| Reuse evaluation machinery behind selected RAE contracts | Less duplication of bridges, grants, monitors, and evaluation tooling. | What semantic mapping and gaps remain? An evaluation framework cannot silently become the language or authority owner. |
| Require one universal gateway and security runtime | Centralizes one deployment's enforcement. | No established requirement here justifies imposing its topology, trust, and operational burden on every RAE use. |

These are candidates, not approved designs.
The current port is neither rejected nor selected as the universal solution.

## Representative walkthroughs before a decision

For each case, identify authored intent, backend choices, selected profiles, operational state, and requested evidence separately.
Record author effort, mappings, deployed components, failure states, and the exact guarantee delivered.

1. Two abstract participants with finite actions, without MCP, machines, or experimental capture.
2. An open concrete environment whose backend resolves unspecified installation detail.
3. Two participants of one role with independent authority and observations.
4. An autonomous participant with manual approval, controller handoff, and cancellation.
5. A human-directed participant using SSH/browser access, distinct from an operator administering the lab.
6. A polymorphic tool whose arguments imply different semantic actions or targets.
7. Concurrent red/blue effects with reverse completion and retained predecessor history.
8. Permitted adversarial influence tracked for research, alongside a strict profile preventing prohibited effects.
9. Disconnection or restart after a native action whose effects are unknown.
10. A supported simulation/emulation composition with explicit time, mapping loss, and observation limits.
11. Operational state without experimental retention, alongside an independently requested detailed capture.

Distinguish missing implementation from missing semantic decisions.
Record unsupported combinations without weakening their controls.
These walkthroughs are architecture review tasks, not an executed evaluation or approved implementation plan.
The existing language-evaluation protocol retains ownership of user-study claims.
No study recruitment, model request, or native lab experiment was performed in this assessment.

## Review sequence and current work

Confirm the product and research tasks this area must support.
Map them to accepted identity, language, control, realization, and evidence authorities.
Compare candidate arrangements using the walkthroughs and external failure models.
Identify decisions that remain adequate, need clarification, or require revision.
Then select the smallest architecture satisfying those tasks and the required extension boundaries.
Only after that review should #1418's implementation plan resume.

Production code and dependency pins are unchanged.
The exploratory feature test and superseded design are retained under `/tmp/lilrae-1418-provisional-*`.
They are not part of the active test suite or accepted architecture.

## References

[intent]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/research/language-extensibility/design-intent.md
[language]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/research/language-extensibility/research.md
[identity]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/decisions/adrs/adr-109-participant-identity-and-objective-assignment.md
[boundary]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/decisions/adrs/adr-085-participant-information-flow-and-control.md
[modular]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md
[mixed]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/research/cross-backend-participant-control/prior-art-and-design-criteria.md
[support]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/explain/reference/revised-control-semantics.md
[evaluation]: https://github.com/OpenRAE/rae/blob/v10.2.0/docs/research/dsl-language-evaluation/index.md
[kubernetes]: https://kubernetes.io/docs/reference/access-authn-authz/authorization/
[kube-admission]: https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/
[envoy]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_authz_filter
[opa]: https://www.openpolicyagent.org/docs/envoy/tutorial-standalone-envoy
[temporal]: https://docs.temporal.io/activity-execution
[ros]: https://design.ros2.org/articles/actions.html
[spiffe]: https://spiffe.io/docs/latest/spiffe-about/overview/
[inspect-approval]: https://inspect.aisi.org.uk/approval.html
[inspect-bridge]: https://inspect.aisi.org.uk/agent-bridge.html
[inspect-code]: https://github.com/UKGovernmentBEIS/inspect_ai/blob/3952947fe19838d23d15146e81b71049142b68f4/src/inspect_ai/agent/_bridge/sandbox/host_tool.py
[inspect-tests]: https://github.com/UKGovernmentBEIS/inspect_ai/blob/3952947fe19838d23d15146e81b71049142b68f4/tests/agent/test_bridge_approval.py
[inspect-design]: https://github.com/UKGovernmentBEIS/inspect_ai/blob/3952947fe19838d23d15146e81b71049142b68f4/design/bridge-host-tool-events.md
[controlarena]: https://control-arena.aisi.org.uk/micro_protocols.html
[controlarena-code]: https://github.com/UKGovernmentBEIS/control-arena/blob/ae0b6fa78ace5a097536eb3464ab5a089740b53e/control_arena/micro_protocol/_defer_to_trusted.py
[openc2]: https://docs.oasis-open.org/openc2/oc2arch/v1.0/oc2arch-v1.0.html
[cacao]: https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.html
[pettingzoo]: https://pettingzoo.farama.org/index.html
[ucef]: https://www.nist.gov/ctl/smart-connected-systems-division/iot-devices-and-infrastructures-group/how-does-ucef-work
[cue]: https://cuelang.org/docs/concept/the-logic-of-cue/
[dsl]: https://inkytonik.github.io/assets/papers/compsurv05.pdf
[cognitive]: https://www.cl.cam.ac.uk/~afb21/CognitiveDimensions/CDtutorial.pdf
[extensions]: https://www.rfc-editor.org/rfc/rfc6709.html
[ai-control]: https://arxiv.org/abs/2312.06942v5
[camel-paper]: https://arxiv.org/abs/2503.18813v2
[camel-code]: https://github.com/google-research/camel-prompt-injection
[fides-paper]: https://arxiv.org/abs/2505.23643v2
[fides-code]: https://github.com/microsoft/fides
