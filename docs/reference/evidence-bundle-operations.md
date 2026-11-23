# Export and verify an evidence bundle

Use this How-to guide for an existing local run archive.
The [bundle reference](evidence-bundle-export.md) defines formats, permissions, and verification limits.
Export does not authorize upload or publication.

## Build a bundle

1. Read the [output permission contract](evidence-bundle-export.md#output-and-source-permissions).
2. Choose the exact run ID and a private output directory outside its run tree.
3. If needed, apply `chmod 700` to that exact existing output directory.
4. Select canonical export or the required projections from the [option reference](evidence-bundle-export.md#export-options).
5. For Parquet, install the existing `parquet` extra or `pyarrow` dependency in the approved environment.
6. Build a canonical bundle:

```shell
lilrae runs export-bundle <run_id> -o ./exports
```

To include the selected JSONL and Parquet projections, run this command:

```shell
lilrae runs export-bundle <run_id> -o ./exports -p jsonl -p parquet
```

Examine the reported path, root identity, member count, seal state, and limitations.
Keep projection limitations with the canonical export result.

## Verify a bundle

1. Read the [verification contract](evidence-bundle-export.md#verification-contract).
2. Run the verifier on the retained archive:

```shell
lilrae runs verify-bundle ./exports/<run_id>.evidence-bundle.tar
```

3. Keep the integrity result and every reported limitation.
4. Before you claim authentication or completeness, examine [seal state](evidence-bundle-export.md#seal-state-and-partial-runs).

## Run store permissions

1. Find the exact configured source store in `run_storage.local_path`.
2. Examine its [permission contract](evidence-bundle-export.md#output-and-source-permissions).
3. Before you change permissions, examine existing entries.
4. To tighten an older store, apply `chmod -R go-rwx` only to the verified store path.
5. Keep redaction enabled before bytes reach persistent storage.
