# ADR-010 · Originals written once, without WORM immutability

**Status:** accepted · **Date:** 2026-10-31

## Context

Originals are the evidence behind every extracted field (REQ-08) and are kept six years. After that, a sole trader may ask
for erasure (REQ-12). Staging is torn down and rebuilt freely.

## Options

1. **Time-based immutability (WORM)** on the `originals` container for six years. Once locked, neither the blobs nor the
   storage account nor the resource group can be deleted before the period ends.
2. **Write-once in code** with versioning and soft delete.

## Decision

Option 2. The app writes each original once (`upload_blob(..., overwrite=False)`, which fails if the blob exists) with its SHA-256 as metadata, and the timeline checks the
hash (`test_timeline_complete`). Storage `stfolium<env>swc` keeps blob versions and a 7-day soft delete for blobs and
containers, has shared-key access and public blob access disabled, and accepts Entra ID only. Lifecycle rules (Bicep): every
blob moves to cool after 30 days without change (CO:10); previous versions are deleted 7 days after they were written, so an
erased original does not outlive its soft-delete window; export files under `exports/` are deleted after 365 days, while the
batches and invoices stay in Cosmos DB. WORM is the client's option: the policy itself has no charge, and its cost is that
the environment can no longer be torn down. It is compatible with REQ-12, which only erases after the retention.

## Consequences

- Restoring a deleted original uses soft delete within 7 days; older originals rely on the write-once code path.
