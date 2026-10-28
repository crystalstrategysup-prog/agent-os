# AgentOS LITE + Atlas + Function Extractor modules (rc2036 candidate)

- `agentos modules` reads a pinned installed module manifest; it grants NO execution rights.
- `agentos project local record/status/sync` keeps source-only accounting under the project's
  `.agentos/lite` without writing `~/.agentos-user/state/turns.lock` for local work.
  Explicit later sync writes a separate additive projection, never legacy READY.
- `agentos atlas` operates on the selected packaged Atlas and project registry.
- `agentos fe` executes the pinned FE 0.4.6 original CLI inside isolated Python
  (`-I`), with embedded FE tools + maintained replay engine; no assumption that
  the target project's `tools/` or `backend/tools` directory is installed.
- Source-only mode has NO authority to change production, credentials, native hooks,
  SQL state or external messaging. An unknown Telegram delivery remains UNKNOWN.
- The FE engine's audit/seccomp trace is a bounded test instrument, not a
  production security certification. Container qualification remains distinct.
- Preserve user overlays in the user home; use the official installer plan,
  expected-current, apply/readback and explicit rollback workflow.

Compatibility: Existing legacy `agentos project enter/ready` remains available and
keeps its full authority checks; new `project local` is explicitly opt-in.

## Safe CLI refusal classification (AgentOS rc2044)

FE refusal keeps `schema: function-extractor.cli/v1`, `status: REFUSED`,
`error_class` and exit2. One reviewed machine code is exposed as optional
`error_code: graph_expansion_cap` for the engine's exact builtin `ValueError`
with that single builtin string argument. This identifies a bounded static
graph refusal; it does not prove source coverage or allow a retry/downgrade.
Unknown reasons, subclasses and arbitrary exception text stay hidden. No
exception string formatting, prefix matching or message passthrough is used.

Preserve STRICT capture, graph limits, unresolved evidence and source pins.
Do not raise caps, use opaque modules or select PARTIAL_STATIC just to obtain
a passing result. Independently qualify a smaller causal boundary or report
the original scope unproved; the diagnostic grants no execution authority.
