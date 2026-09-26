# Public language policy

The canonical public AgentOS distribution is written in English. This applies to
the repository entrypoint, current and historical public documentation, CLI
questions and generated project text, setup scenario data, the documentation
catalog, templates and shipped skills. Personal preferences and private host
instructions remain in the external user overlay.

## Translation boundary

- Preserve stable API and schema identifiers, JSON keys, command names, file names,
  error and status codes, version strings, source references and tested behavior.
- Translate human-facing values and prose without changing the meaning of existing
  security, authority, read-only, no-hook or documentation-first rules.
- Translate historical records faithfully. A translation does not update their
  dated claims or turn them into current authority.
- Keep each `docs/` file identical to its packaged copy under
  `src/agent_os/resources/docs/` when such a copy exists.
- Do not publish unreviewed machine translation as normative text. Review the
  changed source, search for remaining Cyrillic, run the local test suite and
  inspect a built wheel before delivery.

The public foundation currently ships one language. An interactive locale
selection system is a separate feature and must not be inferred from this
translation. Private users may still communicate with their own agents in their
chosen language through their external preferences.
