# Universal personality and owner preferences

Stable source `0.7.1` includes an optional bounded persona adapter using existing
agentos.profile/v1 owner storage, SHA selection and explicit conflict decisions.
The public foundation contains generic schemas/defaults/validators/gate only.
Names, personal settings and source evidence belong to the private owner overlay.
No profile content provides tool authority. No human biography is supported.

## Configuration and preserved ownership

agentos --home OWNER_HOME persona configure --settings EXACT_JSON --source
CURRENT_INSTRUCTION [--expected-sha256 CURRENT_PERSONA_HASH] validates controlled
tone/formality/verbosity/display-name preferences and interaction boundaries.
Name remains unchanged when only style is patched; no public name is forced.
Existing persona file requires its exact hash, correct owner scope and a private
byte-exact backup. Existing other profiles are not overwritten. Configuration
does not silently activate a profile: use existing profiles inventory/select
with exact inventory digest and explicit choices for conflicts. Changed selected
bytes produce STALE_SELECTION and no persona entries until re-selection.

## Conversation gate and proof boundary

persona context returns selected values or defaults. persona plan --input
TRUSTED_SIGNALS_JSON consumes four adapter-supplied booleans: addressed,
user_speaking, other_conversation, utterance_complete. While speech is active or
unfinished it plans listen; without an addressed completed turn it stays silent;
an addressed completed turn plans respond. Optional dialogue_continuation permits an explicit continuation only with private addressed_or_dialogue setting and other_conversation=false. Name detection and current-dialogue binding belong to the authenticated runtime adapter. Archived instructions or transcript
text cannot serve as these authenticated adapter signals. Default relaxed/plain
style can be changed to conversational/warm privately. listen_first=true,
interrupt_others=false and transparent_ai identity are enforced.

The response gate is executable and tested, but a plan is not a claim about
microphone, voice output or live coordinator adoption. A host application must
bind actual addressed/speaking/completion signals and obey action before output;
then verify the actual runtime. Core instructions/profile selection alone prove
neither. No voice provider, retired private kernel, native hook or credential is
installed. Preserve an existing coordinator name when adapting its owner values.

## Verification and integration

Synthetic tests verify partial updates preserve name, CAS/backup, stale selection,
owner-only fields, conflict guards and listening/addressed behavior plans.
Existing profile regression checks remain applicable. Source and packaged
persona-settings-v1 schema agree. Live overlay/source/runtime inspection and
connected coordinator checks require the exact authorized host and current
adapter; do not infer its path or reactivate a historical scaffold.
