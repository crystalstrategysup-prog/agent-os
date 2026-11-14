# API catalogs from existing documentation

`scripts/catalog.py` converts an explicitly selected JSON source to `atlas.semantic-catalog/v1`.
It reads a local file and returns JSON. It does not execute product commands,
HTTP, SSH, dependency installation, or external references.

Sections: [work packets](#bind-a-work-packet), [result meaning](#meaning-of-the-result),
[supported OpenAPI](#openapi-boundaries), [size and history](#size-and-history).

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
Prepare any work bindings below, then pin the final catalog bytes by
`path/bytes/sha256` in `UPSTREAM.semantic_catalog`. The writer saves this one
delta and calls `refresh`; the importer binds cards to document versions.

## Bind a work packet

Compilation does not know which existing work item needs each contract.
Before pinning the catalog, fill its `work_bindings` array with explicit links
from existing source work IDs to generated contract IDs. Set `work_bindings`
to an array like this, replacing the example IDs with actual selected IDs:

```json
[
  {
    "work_id": "WORK-ORDERS",
    "entity_ids": ["CTR-60c1988d2d193d9b7d023f95"]
  }
]
```

Select the contract ID from the compiled `contracts` entries; do not invent an
ID or derive work ownership from its tag. A packet expands declared contract
dependencies, modules and their documents. Add other document IDs explicitly
when that work needs them. If the catalog remains unbound, its cards are visible
globally but a work-specific `packet` may correctly contain no contracts,
modules or documents. After refresh, read the selected work packet and check
its entity IDs. Recompute the catalog pin after any binding edit.

See [Declarative relationship catalogue](upstream-adapter.md#declarative-relationship-catalogue)
for the full binding and patch-link contract. This step preserves the existing
writer and work matrix; it creates no second plan or new execution authority.

## Meaning of the result

`FACT` in a card means that the declaration exists in the pinned document.
`execution=NOT_RUN` is preserved: the compiler does not call APIs. An OpenAPI tag
is a documentation group, not an established data owner. Missing authorization,
input, or result remains `UNKNOWN`. External `$ref` values are not loaded; their
requiredness is not invented. A large value is replaced with an exact pointer
and the SHA of its canonical serialization; the full source remains alongside it.

A compact card or CLI packet is not a self-contained API client specification.
Nested schemas, successful response references, security-scheme definitions,
server URLs and unprojected descriptions may require the original OpenAPI.
Packet documents identify retained files by path, SHA and bytes, rather than
embedding every body. Read those pinned sources before constructing an API call;
neither a catalog import nor a work binding grants permission to execute it.

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

For locally resolved parameter, request-body, and response references in OpenAPI
3.1, a Reference Object's `description` overrides the target description; the
override nearest to the operation wins along a reference chain. OpenAPI 3.0
ignores these reference siblings. Arbitrary sibling fields do not override the
target. Nested Schema Objects retain their original keywords, including `$ref`
and its siblings; the compiler does not evaluate JSON Schema.

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
