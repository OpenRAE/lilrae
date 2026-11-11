# Back Up A Conflicting Search Index

Use this task before resetting a project that contains required Elasticsearch data.
You need authorized access to the affected service and a compatible snapshot repository.
Run it only on an approved isolated lab machine.
The result must be a verified snapshot and a successful restoration check before any destructive reset.

## Prepare A Repository

Inspect the service's existing registered repositories first.
LilRAE does not configure a snapshot repository for this recovery path.
Use the service version's supported [repository setup](https://www.elastic.co/guide/en/elasticsearch/reference/7.17/snapshots-register-repository.html#snapshots-filesystem-repository).
For filesystem storage, mount a separate backup directory and configure `path.repo` before registration.
Restart the service if that configuration requires it.

Keep the repository outside every lab volume that reset removes.
For a remote daemon, the backup directory belongs on the remote engine host.

Until a backup is available, use `lilrae lab stop` without `--volumes` to preserve data.
Do not substitute a tar archive or filesystem copy of the service data directory.
See Elasticsearch's [snapshot warnings](https://www.elastic.co/guide/en/elasticsearch/reference/7.17/snapshot-restore.html#warnings).

## Create And Verify A Snapshot

With the service running, open a project shell in its container.
Replace the repository and snapshot placeholders with an existing repository and a new snapshot name.
Use the reported local endpoint, TLS, and authentication settings.
For the local HTTP example:

```shell
curl -fsS -X POST 'http://localhost:9200/_snapshot/<repository>/_verify'
curl -fsS -X PUT 'http://localhost:9200/_snapshot/<repository>/<snapshot>?wait_for_completion=true'
curl -fsS 'http://localhost:9200/_snapshot/<repository>/<snapshot>'
```

Check that `state` is `SUCCESS` and `shards.failed` is `0`.
Confirm that `indices` contains every required index, including the conflicting index.
The default request includes open indices; verify the actual returned list.

## Prove Restoration

[Test restoration](https://www.elastic.co/guide/en/elasticsearch/reference/7.17/snapshots-restore-snapshot.html#restore-different-cluster) in a separate compatible cluster.
Register its repository read-only and verify the restored data.
Back up required data from other services through their own supported procedures.
An Elasticsearch snapshot does not cover those services.

Return to [unowned-index recovery](index.md#lilrae-lab-start-reports-an-unowned-search-index) only after verification or an explicit data-discard decision.
