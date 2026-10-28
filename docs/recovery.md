# Recovery and integrity

The main `analyze` workflow is restartable. Repeat the same command after Ctrl-C,
process termination or a storage failure. Completed artifacts are immutable and
verified under an OS lock. The current phase keeps its private `.inprogress`
directory; another process waits for the same artifact instead of racing it.

| Phase | Recovery granularity |
| --- | --- |
| Preparation | Ingestion, identifiers, endpoint mapping, canonical edges, degrees, adjacency |
| Native detection | Last completed full pass, including its exact objective |
| CluStRE/Leiden | Restart that detector invocation |
| Quotient/profile/hierarchy/index | Reuse a completed artifact; restart an interrupted artifact |
| Report | Reuse a complete report; rebuild an interrupted report privately |

Checkpoints commit after phase outputs have been written. They are designed for
process interruption, not a power-loss-safe transactional filesystem. An
interrupted phase may repeat substantial work. Generation retains its original
strict contract and does not automatically resume an interrupted synthetic
dataset; keep or move its partial directory before retrying.

An analysis writes `analysis.json` with status and phase. It never replaces a
successful report with a partially rendered one. A report becomes visible only
when it has a manifest and integrity inventory. To use a different input or
algorithm configuration, choose a new output directory. Memory and thread
settings can change during recovery.

## Integrity checks

Every new completed artifact records file sizes and SHA-256 baselines. Normal
reuse checks all lengths and hashes files up to 8 MiB; this avoids repeatedly
scanning multi-gigabyte adjacency arrays. `largegraph-viz verify RUN --deep`
compares every file against its baseline and returns hashes for archiving. This
extra scan is proportional to stored bytes. SHA-256 is not an authenticity
signature: someone able to replace the artifact can also replace its inventory.

`--hash-input` adds content hashing to the input fingerprint. Default file-stat
fingerprints are faster but do not detect an edit that preserves size and mtime.
Keep source inputs immutable while an analysis runs. Cache keys include graph
semantics and algorithm versions; legacy 0.1 caches are not silently trusted by
the new schema. Original archived 0.1 evidence remains readable separately.

If verification detects corruption, move the named artifact directory aside and
repeat the command. Keep it for diagnosis until the rebuild succeeds. Unknown
partial directories are never automatically deleted. Run one large analysis at
a time on an 8 GB computer; locks do not reserve RAM across different jobs.

Disk full: free space on the data and spill volumes, inspect the failing phase,
then repeat the command. The source edge list is never used as scratch storage.
You can increase `--temp-limit` or move `--temp-dir` on retry. Completed cache
artifacts are still reused.

Phase metrics describe the successful builder invocation. Cached artifacts retain
their original producing metrics; time/RSS from interrupted attempts is not
automatically accumulated. Keep each attempt's external cgroup/log record when
measuring recovery costs, and use a fresh cache for uncached performance claims.
