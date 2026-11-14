# API catalogs from existing documentation

`scripts/catalog.py` converts an explicitly selected JSON source to `atlas.semantic-catalog/v1`.
It reads a local file and returns JSON. It does not execute product commands,
HTTP, SSH, dependency installation, or external references.

Three source forms are supported:

| Format | Content transferred |
|---|---|
| `openapi` | OpenAPI 3.0.x and 3.1.x JSON: HTTP methods under `paths`, path and operation parameters, request body, responses, errors, security declarations, and tag groups. |
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

## OpenAPI boundaries

The selected source must be JSON with an `openapi` version of `3.0.x` or `3.1.x`
and a `paths` object. Other versions return `OPENAPI_VERSION_UNSUPPORTED`;
a Swagger 2.0 document without `openapi` returns `OPENAPI_SOURCE_REQUIRED`.
Swagger 2.0, YAML, and other OpenAPI versions need an explicit adapter before
they can be compiled. This reader extracts declarations; it does not validate
every OpenAPI rule or recursively catalog callbacks and webhooks.

Document-local JSON Pointer references are resolved without opening another
file or URL. Resolution stops after 64 reference hops. Parameter, request-body,
and error-response references that are missing, cyclic, external, or longer
than the bound are retained as source declarations. Requiredness of unresolved
parameters and request bodies remains `UNKNOWN`. Distinct unresolved parameter
references remain separate; only parameters with a known `(name, in)` identity
can be overridden by the operation's parameter declaration.

Local Path Item references are followed to enumerate the operations and preserve
their source pointers. A referenced Path Item may add fields absent from its
siblings. Overlapping fields have [undefined behavior in OpenAPI](https://spec.openapis.org/oas/v3.1.1.html#path-item-object) and return
`OPENAPI_PATH_ITEM_REF_CONFLICT`. An unresolved Path Item reference returns
`OPENAPI_PATH_ITEM_REF_UNRESOLVED` because its operations cannot be enumerated
reliably. These refusals do not produce a partial successful catalog.

Explicit parameter schemas such as `false`, `true`, and `{}` are preserved.
The error list retains `4XX`, `5XX`, explicit error status codes, and `default`;
all response declarations also remain in the output field. A range and a more
specific status code are both retained, without inventing runtime behavior.

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
