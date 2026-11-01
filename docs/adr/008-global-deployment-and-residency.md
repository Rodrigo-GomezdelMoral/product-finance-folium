# ADR-008 · Global model deployment and data residency

**Status:** accepted · **Date:** 2026-10-31

## Context

Folium's data rests in `swedencentral`: Cosmos DB, Blob Storage and Service Bus. The app that processes it runs in
`spaincentral` ([ADR-013](013-container-apps-environment-in-spain-central.md)), so storage and the app's processing stay in the EU.
The shared `gpt-5-mini` deployment (`2025-08-07`) is Global Standard, so a request may be processed in any region of
Azure's global capacity. A Data Zone EU deployment keeps inference in the EU for about 10 % more per token, and none exists
in the shared base.

## Options

1. **A Data Zone EU deployment** in the shared base: about +0.5 €/month at the client's volume (10 % of ≈ 5.3 € of model
   tokens), plus quota and ownership of a second deployment.
2. **Keep Global and minimise what the model sees.**

## Decision

Option 2. The normaliser receives the document text Document Intelligence extracted and may fill only the tax lines and the
IRPF withholding (`FILLABLE`, experiment 001); the IBAN never reaches the model; the assistant's tools return no IBAN
(`test_assistant_has_no_write_tool` checks the tool output). `RESPONSIBLE_AI.md` and `PRODUCT.md` state the residency.
Trade-off not applied: Data Zone EU, about 0.5 €/month at client volume.

## Consequences

- A client that requires EU-only inference gets a Data Zone EU deployment and a changed `FOUNDRY_MODEL`; the evaluation gate
  runs against the baseline before the change merges.
- Moving the app to another region keeps this decision only while that region is in the EU (ADR-013).
