# ADR-011 · Scale to zero and cold start

**Status:** accepted · **Date:** 2026-10-31

## Context

The team works Monday to Friday from 08:00 to 19:00 (Europe/Madrid). The Container Apps consumption profile bills nothing
while a revision has no replica. REQ-11 promises 95 % of standard invoices ready for review in under 30 s from upload, and a
replica that starts from zero adds the image pull and the Python start to the first upload.

## Options

1. **Minimum one replica** all month.
2. **A KEDA cron rule** that keeps one replica in business hours: about 3 to 4 €/month at the idle rate (build prompt
   estimate; phase 7 measures it).
3. **Minimum zero,** and measure the cold start before paying for warmth.

## Decision

Option 3 in both environments: zero to two replicas in staging and zero to three in production, an HTTP rule at 20
concurrent requests, so the upload request wakes a replica whose consumer takes the message at once, and the queue rule at
four messages per replica (ADR-005). The startup probe allows two minutes. Phase 7 measures the cold start; option 2 is
applied only if the p95 breaks REQ-11.

**Zone redundancy, not applied.** It needs a VNet-integrated environment and replicas running in several zones, which ends
scale to zero; recovery is a cold one instead (RE:09): redeploy the Bicep, restore Cosmos DB to a point in time and blobs from
versions, within the 4-hour RTO that the phase 7 drill measures.

## Consequences

- Staging ends every phase at zero replicas without any action: the scale rules bring it there after the cool-down period.
- A KEDA cron rule is one more rule in `app.bicep` if the measurement asks for it.
