# Runtime JWT source preservation

The scanner still checks original bytes for recognizable keys and sensitive literal
values. Source classification is not permission, credential validation, an import
resolver or a sandbox. No source/test path is exempted. This grammar only lets the
existing source scanner recognize the exact public Bearer prefix span.

A runtime encode call qualifies only when its namespace has one explicit absolute
module import of jwt (a declared import alias is supported), with no source-wide
rebinding, shadowing, mutation, module alias, unknown reflection or other namespace
use. Direct or reflective encoder/configuration changes decline the new form.
The call has exactly two positional arguments: a dictionary with string keys and
an attribute lookup from a single unmodified absolute imported configuration root.
Only the existing nonliteral runtime lookup grammar can certify that key lookup.
An explicit algorithm is either a known public algorithm label or another proven
imported runtime attribute. Arbitrary calls, literal signing keys, variable/unknown
key origins, unpacked payloads/keywords and unsupported algorithms remain refused.

The resulting AST call identities may be followed through existing bounded name
bindings solely for the Authorization-prefix analysis. Literal RHS values, aliases,
concatenated literal suffixes, nested sensitive dict fields and recognizable keys
elsewhere still refuse the entire input. No computed token or key is obtained.
Input2MiB, AST100000nodes and lookup4096 limits remain. The new form additionally
limits imports64, qualifying encoder calls64 and reflective string targets256.
Exceeding a new bound declines the new form; it does not enlarge old capacity.

Ambiguous shadowing anywhere in the source conservatively declines this form.
Imports here establish a syntactic source binding only, not the actual identity
or behavior of an installed third-party module. The existing external-runtime and
same-UID trust limitations remain; execution and target authority are separate.

Tests cover exact prefix-only spans, aliases of runtime results, unrelated API
patching, no source execution, literal/key/call/shadow/mutation/unknown/recognizable
key/budget refusals, existing forms, and actual indexed capture/restoration in a
disposable fixture. Real source qualification and installed producer checkpoint
are separate evidence. Keep the original refusal and never rewrite its source,
omit the failed changed test or use a bundle as an alternate delivery route.

The same constructor argument proof applies to the existing local-helper return
analysis, so tuple extraction cannot launder a literal signing key. Literal
namespace references, mock patch/import/reload constructs and ambiguous reflection
decline this new form. New analysis is skipped entirely without an explicit jwt
module import. These conservative unsupported cases are not source or target errors.

Pattern captures (match/as/star/mapping-rest) and Python3.12+ type-parameter
bindings also count as shadowing, even though they do not use Name.Store.

Only an encoder-module import can receive the encode-call mutation exception.
A configuration method named encode is still a mutation/unknown origin; another
alias of the encoder module cannot certify a configuration key source.

Dynamic execution/reflection, builtin/importlib/mock imports and frame/global-dict
access conservatively decline the new form, including aliased builtin executors.
This does not change existing non-JWT source forms or grant any new authority.

Before a Python prefix span is accepted, its original byte slice is statically
validated as that exact public string. Alternate-encoding AST offsets cannot
redirect the exception onto a different field or a comment. Original bytes remain.
