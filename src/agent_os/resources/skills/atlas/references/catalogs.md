# API catalogs from existing documentation

`scripts/catalog.py` converts an explicitly selected JSON source to `atlas.semantic-catalog/v1`.
It reads a local file and returns JSON. It does not execute product commands,
HTTP, SSH, dependency installation, or external references.

Three source forms are supported:

| Format | Content transferred |
|---|---|
| `openapi` | Each declared HTTP method/path, path and operation parameters, request body, responses, errors, security declarations, and tag groups. |
| `record-catalog` | Explicit `contracts` records: interfaces, known parameters, result, authorization, ownership, and preserved UNKNOWN values. |
| `operation-registry` | `operations`, `additional_entries`, `workers`: declared inputs, outputs, source pointers, and execution boundaries. |

Create a small configuration file in the selected project:

```json
{
  "schema": "atlas.catalog-source/v1",
  "format": "openapi",
  "path": "docs/openapi.json",
  "document_id": "DOC-API"
}
```

Then obtain the catalog with one static command:

```bash
python3 -B "$atlas_scripts/catalog.py" --root "$project_root" --source docs/catalog-source.json
```

`document_id` is the logical ID of a document already registered in `UPSTREAM.documents`.
Pin the prepared catalog by `path/bytes/sha256` in `UPSTREAM.semantic_catalog`.
The writer saves this one delta and calls `refresh`; the importer binds card
versions to specific document versions. The exact format of additional work and
patch links is described in [upstream-adapter.md](upstream-adapter.md).

## Meaning of the result

`FACT` in a card means that the declaration exists in the pinned document.
`execution=NOT_RUN` is preserved: the compiler does not call APIs. An OpenAPI tag
is a documentation group, not an established data owner. Missing authorization,
input, or result remains `UNKNOWN`. External `$ref` values are not loaded; their
requiredness is not invented. A large value is replaced with an exact pointer
and the SHA of its canonical serialization; the full source remains alongside it.

The catalog does not reopen historically accepted work or assign new product
checks. The scope of earlier acceptance comes from its original receipt. New
checks are needed for the changed area and its criteria.

## Size and history

The current view permits up to 1000 contract cards and 200 documents. The navigation
model is limited to 8 MiB; an individual displayed document to 2 MiB; and the sum
of displayed documents to 16 MiB. A full large catalog can be retained as an input
artifact with a readable index and selected documents pinned. Earlier versions
remain in immutable projection history pages. Accumulating older versions alone
does not exhaust the current view limit.

If one huge document is linked to every card, changing its SHA affects all those
links. For narrow incremental updates, use stable module or API group documents
with explicit source pointers where needed; retain the full original contract
in the archive.
