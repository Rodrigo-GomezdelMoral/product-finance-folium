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
dead-lettering on expiry. The consumer runs four receivers per replica; with at most three replicas, twelve invoices are in
flight, and each spends seconds inside one analyze request, far under 15 requests per second.

**Basic, not Standard.** Standard adds duplicate detection, sessions and topics for a base unit of 0.0118 €/hour, 8.61 €/month
(Retail Prices API, EUR, `swedencentral`, 2026-10-31), against 0.044 € per million operations on Basic. The consumer is
idempotent on the invoice's status and ETag, so duplicate detection would replace no code. Trade-off not applied: Standard,
8.61 €/month.

## Consequences

- One image, one app identity (Data Sender and Data Receiver on the queue only) and one place to read the code.
- The fifth delivery marks the invoice `failed` with its error type and dead-letters the message; production alerts on any
  dead-lettered message (`alert-folium-dead-letters`, a metric alert).
- Basic has no private endpoints: they need Premium (ADR-009).
