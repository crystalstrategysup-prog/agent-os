# Atlas

Atlas is a portable module for controlled development in AgentOS. It connects the
objective, documents and APIs, work items, actors, exact results, and matrix history.

The shared code uses Python 3.11+ and the standard library. Node is required for
interface checks. The navigator builds standalone HTML without a network or server.

## Get started

For an installed project, the normal cycle consists of two commands:

```bash
atlasctl start PROJECT --work ID
# Make a substantive change and send one delta to the current writer.
atlasctl finish PROJECT
```

`start` refreshes the projection and returns the selected work packet. `finish`
publishes a new view only when inputs change. Both commands preserve the existing
source matrix and its writer. Unchanged inputs produce `NO_CHANGE`.

- [Quick start](skills/atlas/references/quickstart.md).
- [Command binding and projects](skills/atlas/references/workspace.md).
- [New, active, or undocumented project](skills/atlas/references/integration.md).
- [Refresh documents with one command](skills/atlas/references/document-sync.md).
- [API catalog](skills/atlas/references/catalogs.md).
- [Data model, history, evidence, and patches](skills/atlas/references/data-contract.md).
- [Modularity, interfaces, and builds](skills/atlas/references/modularity.md).

## Check the code package

```bash
python3 -B check.py
```

The fixed local check suite outputs JSON with Python/Node versions, commands,
exit codes, results, and the SHA of the code checked. This command does not run
product APIs, services, or deployment. DOM tests are not a visual browser review.

## Project data

The skill is in `skills/atlas/`. Its code, schemas, instructions, and synthetic
examples contain no real project bindings. The workspace registry, host routes,
sessions, documents, authoritative source matrices, and receipts belong in the
corresponding project or private AgentOS overlay.

WM-UI sources use `import_matrix.py`: an exact binding, preservation of the original
accepted result as a source claim, and a separate record of unknown criteria.
A new canonical matrix uses the native model in `atlas.py`. Neither mode declares
incomplete documentation complete or revokes prior acceptance for a move to Atlas.

Full matrices are retained as their original bytes; new generations are added to
history. The view and history indexes are read in pages. The selected set and
indexes have size limits reported in `capacity`; reaching a limit does not delete
the immutable archive. The adapter reference defines the exact limits and the
procedure for extending capacity.
