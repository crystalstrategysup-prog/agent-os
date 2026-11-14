# Bounded inventory hashing

`agent_os.safeio.filemap` owns filesystem inventory reads. It returns the same
relative-path to full SHA256 mapping for unchanged supported inputs. Project
lifecycle, source selection and tracked-directory aliases retain their own
existing contracts and call this shared primitive.

## Read and resource boundary

Each regular file is hashed completely from one descriptor in chunks of at most
1 MiB. No content or metadata hash cache is used. File bodies are not allocated
as a single in-memory object. The existing aggregate byte and file-count limits
remain in force; a read may consume at most one additional byte to distinguish
an exact-budget EOF from a file that grew beyond the budget. Excess data raises
`tree_inventory_limit` instead of returning an accepted mapping.

Before hashing, descriptor device, inode, mode, size, mtime and ctime must match
the observed path metadata. After EOF, the descriptor and pathname are checked
again and the consumed length must match. An observed replacement, deletion,
truncation or mutation raises `inventory_file_changed:<relative-path>`. A
non-regular descriptor raises `regular_inventory_file_required:<relative-path>`.
Where supported, opening uses no-follow and nonblocking flags, so a substituted
symlink is refused and a FIFO can be rejected without waiting for its writer.
Descriptors close on both success and failure. Other unchanged-path I/O errors
retain their ordinary error semantics.

## Preserved boundaries

The primitive does not follow file symlinks, exclude additional source, change
tracked alias attestation, expand budgets, modify files, authorize an operation,
or change READY, receipt or UNKNOWN handling. It does not claim an atomic
multi-file filesystem snapshot or protection from a malicious process with the
same user identity. A filesystem with insufficient change evidence still needs
its own stronger isolation or snapshot mechanism when that guarantee is needed.

`tests/test_safeio_inventory.py` exercises full hashes at chunk/budget boundaries,
aggregate limits, bounded allocation, growth, truncation, equal-size rewrites,
replacement, deletion, substituted types and descriptor cleanup. Existing alias
and generated-cache regressions exercise the current inventory read boundary.

## Local comparison, 14 November 2026

The baseline was `safeio.py` from commit
`92bcbd50a2e91c7eb28ce2265445ea10d6b0ef41`. Both implementations read the same
generated 32 MiB file, with an aggregate limit of 40 MiB, three alternating runs
and Python `tracemalloc` enabled. The operating-system cache was not purged.
The fixture is byte `0x78` repeated 33,554,432 times, SHA256
`05f052c8f6da8ee5228ec291820b559c4be183773b9e97a6b82e30dacff85dd3`.
All six returned inventories contained that same complete hash.

| Implementation | Median elapsed seconds | Median peak Python allocation |
| --- | ---: | ---: |
| Baseline whole-file read | 0.038422 | 33,563,242 bytes |
| Streaming full hash | 0.023378 | 2,102,334 bytes |

These measurements qualify this synthetic local workload only. They do not
measure process RSS, cold disk latency, production throughput or the duration
of a complete project lifecycle. The resource guarantee comes from bounded
reads; relative elapsed time depends on the filesystem and environment.
