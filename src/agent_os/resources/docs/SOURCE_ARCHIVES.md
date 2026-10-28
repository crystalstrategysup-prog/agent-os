# Source archives and generated caches

Source inventory, checks, assessment and terminal capture share the versioned
`agentos.source-selection/v2` policy. Exact package-root `.astro`, `.vite`,
`.next`, `.nuxt`, `.svelte-kit`, `.parcel-cache` and `.turbo` directories are
regenerable only when the adjacent bounded regular `package.json` declares the
corresponding generator dependency. Unknown provenance remains source; filenames,
extensions, scanner results, vendor hashes and arbitrary ignore files grant no
exception. Canonical `.astro` components outside the generated directory remain
source. Dependency manifests, locks, configuration, application code, contracts
and immutable Atlas history remain in the inventory under existing bounds.

Registered documents or Git-tracked content under an eligible cache directory
cause a conflict, including an enclosing repository outside a nested selected
project root and Git worktrees. Ancestor discovery reads `.git` metadata only;
unreadable metadata or a failed bounded Git read refuses cache classification.
No source bodies outside the project are inspected and no Git index is written.
Explicit source write paths into that directory also refuse
terminal capture. Cache symlinks are refused, never followed. No cache contents
are opened, hashed, archived or deleted by this classification. The record binds
each exclusion to its path, generator rule and source manifest hash. It is
classification evidence, not proof that an arbitrary build output is safe.
Canonical source must not be authored in generator-owned cache directories.

The READY policy digest pins the source-selection version. Updating this policy
requires fresh admission/readiness and checks for an open task; an old passing
receipt is not inherited. Source files still pass the unchanged secret scanner,
containment, size/hash, authenticated library, clean restore and publication CAS
checks. A rejection remains a rejection, without secret-content classification.

Archives preserve source rather than a runnable dependency/cache tree. The
manifest lists omitted caches, regeneration requirements and external recovery
dependencies. Restore never installs dependencies or runs archived commands.
Use retained package locks and project build instructions in a fresh authorized
environment. Unknown or external dependencies do not become proven restored.

Historical READY snapshots, refused attempts, journals and accepted objects stay
immutable. Never retry a rejected payload under a different identifier or filter
its bytes to bypass scanning. A separately authorized mechanism correction can
lead to a fresh task revision, current source selection, reviewed documents and
new checks, followed by a distinct normal terminal transition. Preserve the old
refusal and do not use its candidate/journal as that transition's input.
