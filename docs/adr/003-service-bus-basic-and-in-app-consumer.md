# ADR-003 · Service Bus Basic and a consumer inside the app

**Status:** accepted · **Date:** 2026-10-31

## Context

An upload must answer at once, while each invoice takes 10 to 30 seconds of Document Intelligence, Prompt Shields and the
model. The month-end peak is about 150 invoices a day, in batches of up to 20. Work must survive a restart or a scale-in and be
retried, and the shared Document Intelligence account allows 15 analyze requests per second for every product on it.

## Options

1. **Background tasks in the request process.** Nothing to deploy, but the work is lost when the replica stops, and there is
   no retry, no dead-letter queue and no signal to scale on.
2. **Azure Functions with a Service Bus trigger.** A second hosting plan, deployment unit and identity, with the workflow, the
   clients and the settings duplicated.
3. **A Container Apps job per message.** One execution and one cold start per invoice, and a second image entry point.
4. **A Service Bus queue and a consumer in the app's lifespan,** scaled by a KEDA rule on the queue.

## Decision

Option 4, with the claim check of the AI-200 Service Bus module: the original stays in Blob Storage and the message carries
only the invoice id. The queue `invoices` (Bicep, `infra/modules/data.bicep`) uses peek-lock with `lockDuration` PT1M, which
`AutoLockRenewer` extends up to 300 s, `maxDeliveryCount` 5, a dead-letter queue, a 14-day time to live (the Basic maximum) and
dead-lettering on expiry. The consumer runs ten receivers per replica (four until 2026-11-01, see below); with at most
three replicas, thirty invoices are in flight, and each spends seconds inside one analyze request, under 15 requests per
second.

**Basic, not Standard.** Standard adds duplicate detection, sessions and topics for a base unit of 0.0118 €/hour, 8.61 €/month
(Retail Prices API, EUR, `swedencentral`, 2026-10-31), against 0.044 € per million operations on Basic. The consumer is
idempotent on the invoice's status and ETag, so duplicate detection would replace no code. Trade-off not applied: Standard,
8.61 €/month.

## Consequences

- One image, one app identity (Data Sender and Data Receiver on the queue only) and one place to read the code.
- The fifth delivery marks the invoice `failed` with its error type and dead-letters the message; production alerts on any
  dead-lettered message (`alert-folium-dead-letters`, a metric alert).
- Basic has no private endpoints: they need Premium (ADR-009).

## Change, 2026-11-01: four to ten receivers per replica

The first staging load test (run 41293079362) gave a p95 time to ready of 41.4 s over normal, peak and soak on the doubles
(REQ-11: under 30 s), and a 20-invoice batch through the real services took 56 s at p50 and 64 s at p95. With two replicas of
four receivers, a batch ran in rounds of about 12 s on the doubles and 13 to 15 s on the real services, and the duplicate
check made each invoice wait for earlier uploads still queued or processing. The replicas were idle meanwhile: peak CPU 0.13
of 0.5 vCPU, because each invoice spends its time waiting on Document Intelligence and the model. Document Intelligence saw 1
to 2 analyze submissions per second, against 15 for the account.

The author raised the receivers to ten per replica in both environments (`CONSUMERS` in `app/main.py`), and the queue rule's
`messageCount` to ten with it, so a 20-invoice batch runs in one round on two replicas and the scaler adds a replica
per ten waiting messages. At most 20 invoices are in flight in staging and 30 in production (60 during a production canary,
ADR-005); at about 7.5 s per analysis that is at most about 8 submissions per second, still under 15. If CPU or memory
becomes the limit, the receivers come down before the replicas go up.

**Measured, 2026-11-01 (run 41299957986):** p95 ready 24.2 s over normal, peak and soak and 100 % availability, both SLAs
met; a 20-invoice batch on the doubles 27 s at p50 and 41 s at p95 (36 s and 56 s with four receivers); through the real
services 44 s and 49 s from the click (56 s and 64 s). Peak CPU 0.18 of 0.5 vCPU, memory under 0.5 GB: neither is the limit.
