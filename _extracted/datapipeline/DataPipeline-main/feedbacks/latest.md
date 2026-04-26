Phase 3 Review and Phase 4 Start Feedback
Status

Phase 3 is accepted as complete enough to move forward.

This does not mean the system is “done.” It means the project has crossed the line from:

market data plumbing
into
a real machine-native dataset system with a compiler path, trust gate, and first nonhuman feature release.

From the Phase 3 repo state and coordination logs, the important things landed:

Agent 1 published the state substrate with typed tick/state/window refs and rolling state-window support through mt5pipe.state.public.
Agent 2 shipped the first stable machine-native feature families:
disagreement/*
event_shape/*
entropy/*
and exposed the relevant public loaders/helpers through features.public and labels.public.
Compiler/truth/catalog boundaries were restored and documented, after earlier blocking issues around compiler public importability and missing truth service were resolved.

That is enough to treat Phase 3 as a real checkpoint.

What Phase 3 got right
1. The architecture is finally coherent

The repo is no longer “a pipeline plus random scripts.”
It now behaves like a modular monolith with:

shared contracts
public boundaries
sector ownership
coordination logs
contract change logging
a human feedback inbox

That is the correct foundation.

2. The state substrate became usable

The state layer is no longer just merged bars and some convenience loaders.
It now has:

typed artifact refs
typed window requests
rolling state-window materialization
public exports other sectors can build against

That matters because machine-native features need state windows, not just candles.

3. The first machine-native families are real

The project now has a real first-generation machine-native feature release, not just “more indicators.”

The three families that matter for this checkpoint are:

disagreement/*
event_shape/*
entropy/*

That is the right first cut.
It is rich enough to matter, but not so broad that the repo collapses under feature sprawl.

4. The compiler path is the center of gravity now

This is one of the most important shifts in the entire project.

The compiler path, trust gate, manifesting, and catalog are now the main route for serious datasets.
That is the difference between:

“we can generate data”
and
“we can generate reproducible, inspectable research artifacts”
5. Coordination discipline improved

The agents are now using:

chat/contracts.md
chat/coordination.md
per-agent logs
human feedback flow

And the best sign is not that they talked a lot.
The best sign is that they used those files for the right things:

state substrate handoff
feature family handoff
boundary changes
blockers

That is the behavior to preserve.

What is still not good enough to forget forever

Phase 3 is complete, but it is not “institutional-final.”

The system is still weak in these areas:

1. Coverage depth and real historical density

The architecture is good, but the entire value of the system still depends on synchronized, point-in-time-correct, overlap-rich history.

This remains a real risk:

sparse periods
merge overlap quality varying by day/session
gap behavior
source asymmetry
thin windows that look good in demos but are weak across long ranges

Phase 4 must treat coverage quality as a first-class concern.

2. Truth is present, but not fully mature

The trust gate exists, which is a huge step.
But Phase 4 needs to make it harder, more precise, and more useful.

Specifically:

better family-level missingness thresholds
drift awareness
stronger split integrity / purge / embargo validation
stronger dataset acceptance/rejection reasoning
clearer source-quality impact on artifact acceptance

Phase 3 truth is enough to publish a baseline nonhuman dataset.
It is not yet enough to let you trust the whole platform blindly.

3. Feature richness is still first-wave

The first machine-native families are real, but they are still only the first wave.

Phase 4 should not become an uncontrolled feature explosion.
It should expand only where it improves:

robustness
non-human state representation
model usefulness
dataset trust
4. The model research layer is still behind the data layer

This is expected.
But it means the project is still stronger at “building the artifact” than at “proving the artifact is actually the best research input for training.”

That is a Phase 4 problem.

What must be frozen before Phase 4 starts

These things should be treated as stable unless there is a very good reason to change them:

Freeze these:
package ownership boundaries
public boundary modules
the shared contracts pattern
chat/contracts.md as the source of boundary truth
chat/coordination.md as coordination only
feedbacks/latest.md as the human steering layer
the Phase 3 machine-native dataset baseline
the compiler-first artifact flow
the trust-gated publication rule
Do not casually redesign:
merge logic
raw backfill flow
package structure
compiler public surface
manifest addressing
trust report shape
the meaning of the current Phase 3 selectors

If any of those must change, it has to be deliberate, documented, and justified.

What Phase 4 should actually be

Phase 4 should not be “add every cool feature idea.”

Phase 4 should be:

Hardening, expansion, and research-grade validation of the Dataset OS

That means the center of gravity should move to:

1. Data quality and trust hardening

Improve:

coverage metrics
source-quality metrics
feature-family missingness metrics
artifact validity rules
trust scoring clarity
failure reasons
dataset acceptance thresholds
2. Better label maturity

Strengthen:

multi-horizon label packs
volatility-scaled labels
label balance reporting
purge/embargo correctness
exclusion windows for bad conditions
3. Better machine-native feature breadth, but only selectively

Add more only if it is justified and stable.

Good candidates for Phase 4:

one stronger multiscale family
one stronger latent/regime family
possibly one spectral family if it stays clean

Bad Phase 4 behavior:

shipping 10 fancy families with weak tests and weak trust gating
4. Research harness maturity

Phase 4 should improve:

ablations
dataset diff usefulness
trust-report interpretability
compile/inspect/diff ergonomics
baseline research comparability
5. Coverage scaling

Phase 4 should expand:

synchronized date ranges
daily QA over wider windows
better gap intelligence
better confidence in overlap quality
What not to do in Phase 4

Do not do these unless they are explicitly justified later:

do not redesign the entire architecture again
do not split into runtime microservices
do not chase “perfect institutional finality”
do not build exotic math families just because they sound impressive
do not break current public boundaries casually
do not weaken truth just to make a dataset pass
do not let agent coordination drift back into ad hoc chaos
do not treat one clean test run as proof of long-horizon dataset quality
Recommended Phase 4 priorities
Priority 1

Harden the nonhuman dataset path:

make xau_m1_nonhuman_v1 boringly reliable
improve trust diagnostics
improve coverage reporting
improve family-level QA
Priority 2

Add one more carefully chosen feature family only if justified by the current dataset/compiler/truth path

Possible candidates:

multiscale consistency
latent-state / regime probability
light spectral family

Only one of these should be allowed initially unless the first expansion is extremely clean.

Priority 3

Strengthen label quality and label diagnostics

Priority 4

Strengthen inspect/diff/trust workflows for actual research use

Priority 5

Expand synchronized coverage and prove the dataset path over longer windows, not just narrow slices

Agent guidance for Phase 4
Agent 1

Focus on:

state quality
coverage intelligence
better state-window substrate
source-quality metadata
stronger artifact refs / state manifests if needed

Do not wander into feature creativity.

Agent 2

Focus on:

selectively expanding machine-native features
improving registry quality
PIT safety
family-level tests
label maturity where needed

Do not explode the feature space.

Agent 3

Focus on:

compiler/truth/catalog hardening
inspect/diff usefulness
publication gates
trust report quality
research artifact usability

Do not under-log boundary changes again.

Phase 4 acceptance criteria

Phase 4 should be considered complete only if all of the following are true:

The current nonhuman dataset path is stable over a wider synchronized range
Trust gating is stricter and more informative than in Phase 3
At least one additional meaningful improvement landed in either:
feature fabric
label maturity
trust/reporting quality
Compiler-produced artifacts remain reproducible and inspectable
Boundary discipline and human-feedback discipline remain intact
No major regression in public surfaces or artifact semantics occurred without proper logging
Final verdict

Phase 3 succeeded.

That means you should not go into Phase 4 with panic or with architecture churn.

You should go into Phase 4 with discipline:

freeze what worked
harden what is still weak
expand only where it meaningfully improves the dataset OS
keep the compiler/truth path as the center of gravity

The system is now good enough that the wrong move is no longer “not enough structure.”

The wrong move now would be:
too much ambition without enough gating.

Phase 4 should be ambitious, but controlled.

Required behavior before new work starts

All agents must:

read this file before starting Phase 4 work
summarize in their agent log what parts of this feedback they are acting on
log any conflict with their current prompt in chat/coordination.md
keep using chat/contracts.md for public boundary changes only