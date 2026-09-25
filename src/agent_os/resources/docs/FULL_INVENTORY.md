# Full Inventory

Full Inventory is a bounded map of maintained project knowledge. It is not a
home-directory crawler, search index or archive.

The catalog explicitly registers project roots. AgentOS then classifies known
surfaces as `project`, `roadmap`, `skill`, `problem`, `host` or `history` and
records their paths, sizes and SHA-256 identities. File contents are never
included. Historical artifacts are marked `HISTORICAL_EVIDENCE`, have retrieval
disabled and are excluded from the default selection.

```bash
agentos inventory collect \
  --catalog /absolute/path/projects.json \
  --output ~/.agent-os/state/inventory.json

agentos inventory select \
  --input ~/.agent-os/state/inventory.json \
  --project-id my-project
```

Catalog and inventory inputs must be canonical absolute, non-symlink regular
files. Project roots must be explicitly registered canonical directories.
Symlink traversal, hard-linked knowledge files, duplicate JSON keys, duplicate
roots, path traversal, file-count overflow, byte overflow and changed bytes fail
closed.

The inventory tells an agent where maintained truth lives. It does not declare
that every file is correct, grant runtime authority or replace review.
