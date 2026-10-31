# ADR-004 · Cosmos DB for NoSQL serverless, not Azure SQL

**Status:** accepted · **Date:** 2026-10-31

## Context

Folium stores documents: an invoice with its lines, findings, duplicates and timeline; append-only audit entries; export
batches; the vendor master; the assistant's conversations; and the workflow's checkpoints. Agent Framework already stores the
last two in Cosmos DB (`CosmosCheckpointStorage`, `CosmosHistoryProvider`). The volume is about 1,500 invoices a month, in
bursts, and nothing should bill by the hour while nobody works.

## Options

1. **Azure SQL Database serverless.** Auto-pause, relational queries and ledger tables, but the checkpoints and the history
   would need storage code of their own and a schema to migrate.
2. **Cosmos DB with provisioned throughput.** Predictable latency, but billed every hour at the minimum throughput.
3. **Cosmos DB serverless.** Billed per request unit (0.268 € per million RU) and per GB stored; the framework's integrations
   work unchanged.

## Decision

Option 3: account `cosmos-folium-<env>-swc`, database `folium` and six containers declared in Bicep, each with the partition
key the code uses: `invoices` and `exports` on `/id`, `audit` on `/invoice_id`, `vendors` on `/tax_id`, `conversations` on
`/session_id` (the history provider's key) and `checkpoints` on `/workflow_name`. Local (key) authentication is disabled; the
app identity holds the built-in Data Contributor SQL role on the database only, created by the Bicep through the CI
principal's `Contributor` role. Continuous backup with the 7-day tier, which has no charge, gives point-in-time restore for the
restore drill (RPO 15 minutes).

**Cross-partition queries.** Listing invoices by status and finding duplicate candidates query `invoices` across partitions,
bounded by `TOP`. At 1,500 invoices a month this costs a few RU per query. At ten times the volume, a container partitioned
by vendor tax ID for the duplicate check would be the first change.

## Consequences

- Single region, no zone redundancy (ADR-011): recovery is a point-in-time restore into a new account.
- The emulator (vNext, preview) runs the same code locally; the key it needs is set only in the shell, never in Azure.
