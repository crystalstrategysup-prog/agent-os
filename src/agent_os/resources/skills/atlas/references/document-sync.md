# Updating pinned documentation

`sync_docs.py` updates the local copy of already connected project documentation, its inventory, and the compiled API catalog. It then calls the existing `import_matrix.refresh` so documents and work appear in one projection. The authoritative matrix and product files retain their existing writer.

## Commands

Through the installed workspace façade:

```sh
atlasctl docs PROJECT --source-root /absolute/prepared-documents
atlasctl docs-reconcile PROJECT
atlasctl docs-reconcile PROJECT --finish-pending
```

Without the installed short name, prefix the same commands with `python3 -B scripts/workspace.py --registry /absolute/PROJECTS.json`. Direct API: `sync_docs.update(root, source_root, binding_path=".atlas/UPSTREAM.json")` and `sync_docs.reconcile(root, binding_path=".atlas/UPSTREAM.json", finish_pending=False)`.

The source is an explicitly selected, prepared documentation directory. This module does not download host data, execute documented APIs, or determine that an arbitrary file is safe to include from its extension alone. It is not a secret filter: the content of permitted files is preserved exactly, including the history of earlier bytes. Source preparation must exclude credentials, tokens, and unrelated data before running an update.

## Preconditions and write scope

An active `.atlas/UPSTREAM.json`, a complete local documentation copy, and an `.atlas/DOCUMENT_SYNC.json` configuration with schema `atlas.document-sync/v1` are required:

| Field | Purpose |
|---|---|
| `destination` | Copy directory under `work/atlas-sources/`. |
| `inventory` | Pinned `atlas.project-document-snapshot/v1` with `offline_index_only: false`. |
| `catalog_spec` | Explicit `atlas.catalog-source/v1` under `.atlas/`, defining the API source and format. |
| `semantic_catalog` | The catalog linked to UPSTREAM under `work/atlas-sources/`. |
| `record_index` | Optional relative path to the publisher index; permits verification of contract catalog record IDs and SHAs. |

Writes are limited to the authorized copy, its inventory/catalog, the selected binding, and the updater's journal under `.atlas/doc-sync/`. Overlap with the authoritative matrix or its history is forbidden. Symlinks, escaping relative paths, hidden files, and unknown file types cause refusal.

## What updates automatically

Existing files must match the inventory before writing. Their new version is retained together with the exact previous version. If an inventory JSON, binding, or semantic catalog has not changed semantically, its original bytes are preserved: reformatting administrative JSON alone does not create a new project version.

A new `.md` file of up to 512 KiB can be added to the reading set and binding automatically; its ID is stably derived from the path. The entire reading set permits fewer than 180 files and at most 6 MiB. A larger new Markdown file is retained in the overall inventory without automatic inclusion in the reading set. Each selected document is limited to 2 MiB and must be UTF-8 without NUL; selected JSON is also syntax checked. The inventory for viewing is limited to 2 MiB. These checks run before copies are replaced.

The updater does not accept new `.json`, `.yaml`, `.yml`, or `.txt` files. Including them requires separate explicit registration or a set migration by the current writer; existing registered metadata, catalog, and index files update within the prior binding. The source has overall limits of 2000 files, 64 MiB, and 8 MiB per file read. These are technical limits for one update, not an assessment of project-wide completeness.

Deleting a previously pinned document requires an explicit retirement decision. Changing the root binding, writer, scope, or source schema is also a separate migration. Do not edit the inventory merely to bypass a check.

The catalog recompiles only derived `modules`, `contracts`, and `relations`. Intentionally declared `work_bindings`, `work_context`, and `patch_bindings` are preserved. If derived cards were manually edited, the update stops with `MANUAL_CATALOG_EDITS_REQUIRE_RECONCILE`; removed linked contracts and a changed patch base require a decision by the current writer. Recompiling the catalog does not turn a source execution or acceptance claim into runtime evidence.

## Lifecycle and recovery

One shared `IMPORT.lock` serializes cooperating projection and documentation writers. Before replacing files, the updater records the plan, SHAs, and exact before/after bytes in its own journal generation, then creates `DOC_SYNC_PENDING.json`. Each replacement checks the expected original bytes and reads the result back.

If execution stops with pending state, first run `docs-reconcile PROJECT`. This read shows each destination as `BEFORE`, `AFTER`, or `CONFLICT`. The regular importer refuses to refresh the projection while document sync is pending.

`docs-reconcile PROJECT --finish-pending` continues that exact pinned plan: it leaves already written `AFTER` files in place, writes `BEFORE` files, then performs the refresh. On `CONFLICT`, intervening bytes are not overwritten. Recovery does not accept a new source root. A remaining lock is not removed automatically; an incomplete journal without active pending state is not arbitrarily activated either. These cases require reconciliation of the original operation and its write boundary.

A successful document update returns `DOCUMENT_SNAPSHOT_UPDATED` and a nested `projection`. Top-level `NO_CHANGE` means there was no documentation delta; `projection.status` separately reports the authoritative matrix refresh result. If all inputs are unchanged, both parts return `NO_CHANGE`, without a new release or rewriting existing files. The document update receipt confirms local copies and their catalog; it does not confirm product tests, runtime acceptance, or remote host freshness.
