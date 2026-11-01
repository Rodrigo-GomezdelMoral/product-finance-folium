# ADR-011 · Scale to zero and cold start

**Status:** accepted, amended 2026-11-01 (option 2 in production) · **Date:** 2026-10-31

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
four messages per replica (ADR-005; ten since 2026-11-01, ADR-003). The startup probe allows two minutes. Phase 7 measures
the cold start; option 2 is applied only if the p95 breaks REQ-11.

**Zone redundancy, not applied.** It needs a VNet-integrated environment and replicas running in several zones, which ends
scale to zero; recovery is a cold one instead (RE:09): redeploy the Bicep, restore Cosmos DB to a point in time and blobs from
versions, within the 4-hour RTO that the phase 7 drill measures.

## Consequences

- Staging ends every phase at zero replicas without any action: the scale rules bring it there after the cool-down period.
- The KEDA cron rule is one more rule in `app.bicep`, added in production only on 2026-11-01 (below).

## Measured in staging (2026-11-01)

One one-page invoice uploaded with the app at zero replicas, through the real services:

| Step | Time |
|---|---|
| Upload request until the replica is scheduled and the container starts | 16 s (platform scheduling 15 s, image already cached, container create 1.5 s) |
| First startup probe, 0.7 s after start, fails; the next comes 12 s later (`periodSeconds` 12) | 13 s |
| Not broken down by the platform logs: the request reaching the platform, the app answering, ingress | ≈ 6 s |
| Upload answered (`202`), measured by the client | **35.3 s** from the click |
| Ready for review after the `202` | 13.3 s |
| **First invoice after idle, from the click** | **≈ 49 s** |

A warm upload of six invoices was answered in 2.6 s and its invoices were ready in 11.9 to 24.4 s. REQ-11 is measured as
`invoice_ready − invoice_uploaded`, and `invoice_uploaded` is written once the replica answers, so the metric does not see the
cold start: the first batch after five idle minutes waits about 35 s more than the metric says. The choice between option 2
in production (about 3 to 4 €/month) and keeping option 3 with the metric as defined is the author's. A shorter startup probe period would save up to 9 s, but at
most 10 failures are allowed, so it would also shorten the two-minute start window.

## Decision, 2026-11-01: option 2 in production

The author chose option 2 in **production only**. A custom rule `business-hours` of KEDA type `cron` (Learn, *Scaling in
Azure Container Apps*, updated 2026-05-20: a custom rule takes any ScaledObject-based KEDA scaler) keeps one replica from
`0 8 * * 1-5` to `0 19 * * 1-5` in `Europe/Madrid`, the team's hours and REQ-10's window. `minReplicas` stays 0, so the
replica count is the highest any rule asks for: one in business hours, more when the queue or HTTP rule asks, zero at
night and at weekends. The first upload of the day no longer waits the ≈ 35 s cold start measured above. Staging keeps
option 3 and still ends every phase at zero replicas.

**Cost:** about 242 hours a month (11 hours on about 22 weekdays) of one 0.5 vCPU, 1 GiB replica at the idle rate while it
waits, about 3 to 4 €/month: the build prompt's estimate. The Retail Prices API returned only the free-grant rows of the idle
meters on 2026-11-01, so Cost Management confirms the figure after a month in production (`docs/cost.md`). The monthly free
grant is per subscription and shared with other products, so it is not counted.
