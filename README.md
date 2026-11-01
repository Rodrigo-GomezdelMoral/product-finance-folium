# <img src="docs/images/brand/folium-icon.svg" alt="" height="40"> Folium

Built by **Rodrigo Martín Gómez del Moral Herranz**

<a href="https://github.com/Rodrigo-GomezdelMoral"><img src="docs/images/author/github.png" alt="GitHub" height="36"></a>&nbsp;&nbsp;<a href="https://www.linkedin.com/in/rodrigo-mart%C3%ADn-g%C3%B3mez-del-moral-herranz"><img src="docs/images/author/linkedin.png" alt="LinkedIn" height="36"></a>&nbsp;&nbsp;<a href="https://rodrigogomezdelmoralherranz.es"><img src="docs/images/author/portfolio.png" alt="Portfolio" height="36"></a>

Supplier invoices extracted, validated and de-duplicated, with human review and ERP export, for an accounts payable team that
keys 1,500 invoices a month by hand at 9 to 19 minutes each. In staging, 95 % of invoices are ready for review in 24.2 s
under load (the AI services behind doubles with their measured latencies), a batch of three through the real services in
about 13 s, and the AI never approves or exports anything.

**Try it:** [the published demo](https://rodrigo-gomezdelmoral.github.io/product-finance-folium/) replays runs recorded from
the deployed system, with their real timings, in the same interface.

## The problem

A mid-size Spanish wholesale distributor receives about 1,500 invoices a month from about 400 vendors, as PDFs and scans, with a
month-end peak of about 150 a day. Three clerks key every one of them into the ERP: read it, look up the vendor, key the header and
the lines, check the totals and VAT by hand, search for a duplicate and file the PDF. That is 225 to 475 hours a month, and the
mistakes it lets through, an invoice entered twice or a wrong tax line, surface only at reconciliation.

![Accounts payable today: eight manual steps by the clerk, 9 to 19 minutes per invoice](docs/images/process-as-is.svg)

## What it does

- Reads each invoice with Document Intelligence and returns every field with its confidence and the place on the page it came from.
- Normalises it to one schema and matches the vendor, calling a model only where a rule cannot decide, and rejects any value the
  model did not read in the document.
- Validates Spanish VAT and IRPF rates, tax IDs, dates and arithmetic, and blocks exact and probable duplicates.
- Puts the original next to the fields for the clerk; invoices with findings go to the lead, and the AI never approves or exports.
- Exports approved invoices in the ERP layout exactly once, with a timeline of every step and decision.

The clerk's work per invoice becomes a review of a prepared card, with a target of 2 minutes instead of 9 to 19.

![Accounts payable with Folium: the clerk uploads and reviews, Folium prepares each invoice, the lead resolves findings and exports](docs/images/process-to-be.svg)

## Requirements

Every acceptance criterion is in [`docs/PRODUCT.md`](docs/PRODUCT.md). Status on 2026-11-01: every Must is implemented,
tested and deployed to staging, where it was used through the web; production receives the same image with `v1.0.0`.

| ID | Priority | Requirement | Evidence |
|---|---|---|---|
| REQ-01 | Must | Upload one invoice or a batch of up to 20 | batch of six (PDF, scan, JPEG) ready in 12 to 24 s in staging |
| REQ-02 | Must | Extract every field with its confidence and source | header accuracy 0.9937 on 60 invoices; low-confidence fields marked on the card |
| REQ-03 | Must | Normalise to the canonical schema and match the vendor | vendors matched in staging; the model cannot add a value absent from the document |
| REQ-04 | Must | Validate mandatory fields, arithmetic, tax rates, tax IDs and dates | finding precision and recall 1.00; invoices with findings decided by the lead in staging |
| REQ-05 | Must | Detect exact and probable duplicates | duplicate precision and recall 1.00; exact duplicates sent to the lead and rejected in staging |
| REQ-06 | Must | Review and correct, with every correction recorded | corrections in the timeline and the `field_corrected` event in staging |
| REQ-07 | Must | Export approved invoices exactly once in the ERP layout | the same `Idempotency-Key` twice returns one batch in staging |
| REQ-08 | Must | Full traceability per invoice | timeline with model and prompt versions; resume from a checkpoint exactly once |
| REQ-09 | Should | Read-only assistant with cited answers | groundedness 4.2 to 4.65, citations 1.00; no write tool |
| REQ-10 | Must · SLA | 99.5 % availability in business hours | **100 %** measured under load, 2026-11-01 |
| REQ-11 | Must · SLA | 95 % of standard invoices ready for review in under 30 s | **24.2 s** p95 measured under load, 2026-11-01 |
| REQ-12 | Should | Erasure of a sole trader's personal data on request | `ops/erase.py`, tested; not run in staging |

### Traceability

| REQ | Phase | Test | Live evidence | Demo run |
|---|---|---|---|---|
| 01 | 1, 4 | `test_upload_batch_hash_and_types` | batch upload in staging | Batch upload ready for review |
| 02 | 2 | `test_extract_maps_all_fields` (recorded responses) | ready invoice in staging | Batch upload ready for review |
| 03 | 2 | `test_normalizer_cross_check_rejects_invented_values`, `test_vendor_matched_by_tax_id_then_name` | vendor matched in staging | Correction and approval |
| 04 | 1 | `test_rules_type_each_failure_with_its_evidence`, `test_rules_check_nif_cif_and_eu_vat`, `test_rules_on_the_synthetic_set` | invoice with findings | Invoice with findings decided by the lead |
| 05 | 1, 4 | `test_duplicates_exact_and_probable`, `test_duplicate_blocks_export` | duplicate blocked | Probable duplicate blocked |
| 06 | 4, 5 | `test_correction_recorded`, `test_clerk_cannot_approve_findings` | correction in the timeline | Correction and approval |
| 07 | 4 | `test_export_exactly_once` | two exports, one batch | Export exactly once |
| 08 | 2, 4 | `test_timeline_complete`, `test_resume_from_checkpoint`, `test_redelivered_message_is_a_noop` | timeline in staging | Timeline of an exported invoice |
| 09 | 2, 3 | `test_assistant_has_no_write_tool`, `test_injected_invoice_skips_the_normalizer`, evaluation citations | cited answer and refused injection | Assistant answer with citations · Hidden instructions refused |
| 10 | 7 | Locust, workbook | availability measured | the load test results below |
| 11 | 7 | Locust, `invoice_ready` | p95 measured | Batch upload ready for review |
| 12 | 4 | `test_erase_redacts_personal_fields` | not run in staging | not recorded |

## KPIs

Measured from Application Insights `customEvents`, which are never sampled out. The staging values come from the operator's
tests on 2026-11-01, not from client use; production measures the client's.

| KPI | Target | Staging, 2026-11-01 |
|---|---|---|
| Handling time per invoice | 2 min or less, from 9 to 19 today | median 35 s over 6 approvals |
| Touchless rate | 70 % or more approved with no correction | 83 % (5 of 6) |
| Field correction rate | 5 % or less of extracted fields | 1 corrected field over 6 approved invoices |
| Feedback | 80 % or more positive | no feedback yet |

## Repo card

| | |
|---|---|
| Type | AI product: accounts payable invoice processing for a mid-size wholesale distributor |
| Client and users | the accounts payable team: clerks upload and review, the lead decides findings and exports |
| Azure services | per environment: Container Apps with built-in Entra sign-in, Cosmos DB for NoSQL serverless, Blob Storage, Service Bus Basic, Application Insights, workbook, budgets; SLO alerts in production. Shared: Foundry (`gpt-5-mini`, Document Intelligence, Prompt Shields), Container Registry, Log Analytics |
| AI | Document Intelligence `prebuilt-invoice`; `gpt-5-mini` 2025-08-07 pinned; Microsoft Agent Framework: a graph workflow per invoice with checkpoints and human review, one normaliser agent and a read-only assistant, self-hosted |
| Stack | Python 3.12, FastAPI, Agent Framework; React, TypeScript and Vite in the common product interface |
| Environments and delivery | local with emulators; staging on every merge and production on every release, one image per merge deployed by digest; GitHub Actions with OIDC, no secrets |
| Security | managed identities and local auth off everywhere, app roles `Invoice.Process` and `Invoice.Approve`, HTTPS only, Prompt Shields on every document, no write tool for any model |
| SLA | availability 99.5 % (measured 100 %), p95 ready under 30 s (measured 24.2 s) |
| Demo | [rodrigo-gomezdelmoral.github.io/product-finance-folium](https://rodrigo-gomezdelmoral.github.io/product-finance-folium/) |

## Architecture

One container app serves the web client and the API and runs the queue consumer. An upload is stored in Blob Storage and
Cosmos DB and queued in Service Bus; the consumer runs the invoice's workflow (extract, shield, normalise, validate, check
duplicates, request review) and saves its checkpoints in Cosmos DB, so a review resumes it on any replica. KEDA scales the
app on HTTP requests and on the queue, from zero.

The app and its environment run in `spaincentral`; data, telemetry and the shared AI services are in `swedencentral`
([ADR-013](docs/adr/013-container-apps-environment-in-spain-central.md)).

## How it works

- **A function before an agent.** The rules, the duplicate check, the vendor match and the export are plain functions. The
  one agent fills only what the extraction could not read, and every value it proposes must be printed in the document
  ([ADR-002](docs/adr/002-one-agent-where-a-function-cannot.md)).
- **Human in the loop by construction.** The workflow pauses with a review request; only a person's decision resumes it, from
  its checkpoint, exactly once. A clerk cannot approve an invoice with an open finding or a duplicate
  ([ADR-001](docs/adr/001-graph-workflow.md)).
- **Evaluation gate.** Every pull request that touches the agents, prompts or workflow runs the smoke suite against the
  baseline ([`docs/evaluation.md`](docs/evaluation.md)).

## In action

The [published demo](https://rodrigo-gomezdelmoral.github.io/product-finance-folium/) holds runs recorded from staging by [`ops/record.py`](ops/record.py): a batch upload ready for review, a correction and approval, an invoice with
findings decided by the lead, a probable duplicate blocked, hidden instructions refused by Prompt Shields, an export exactly
once, an exported invoice's timeline, and the assistant's cited answers.

## Environments and releases

| | Staging | Production |
|---|---|---|
| Changed by | `deploy.yml`, on every merge to `main` | `release.yml`, on a published release, after the author's approval |
| Replicas | 0 to 2 | 0 to 3, one kept in business hours |
| Alerts | none | availability, p95 ready, errors, dead letters |

Every merge builds one image, deploys its digest to staging behind a canary label, checks health and runs a smoke test. A
release checks that its commit was deployed and passed the load test, then promotes the same digest to production: 10 % of
traffic for ten minutes watching server errors, then 100 %, or a rollback. Rollback is a release of an earlier tag.

**Load tests in staging** (`load-test.yml`, run 41299957986, 2026-11-01), with Document Intelligence and the model behind
doubles that keep their measured latencies:

| Scenario | p50 | p95 | p99 | Requests/s | Errors | Replicas |
|---|---|---|---|---|---|---|
| normal, 5 users | 16 s | 30 s | 30 s | 0.83 | 0 of 25 uploads | 2 |
| peak, three 20-invoice batches | 27 s | 41 s | 41 s | 2.83 | 0 | 2 |
| soak, 30 min | 16 s | 16 s | 17 s | 0.73 | 0 of 150 uploads | 2 |
| stress, ramp to about 105 users | 16 s | 27 s | 29 s | 8.94 | 0 of 616 uploads | 2 |
| 20 invoices, real services | 44 s | 49 s | 49 s | 2.16 | 0 | 1 to 2 |

**SLOs measured:** p95 ready 24.2 s against an SLO of 25 s and an SLA of 30 s; availability 100 % against 99.7 % and 99.5 %.
Cold start from zero: 35.3 s to the upload's answer. Restore drill: Cosmos DB point-in-time restore in 11 minutes, a blob
version in 13 s. **DORA metrics** are read from the workflow runs as described in [`docs/OPERATIONS.md`](docs/OPERATIONS.md),
from the first release on.

## Cost

| | At rest | In use | Budget |
|---|---|---|---|
| Staging | about 0.3 €/month | about 7 €/month | 10 € |
| Production | about 1.5 €/month, plus 3 to 4 € for the business-hours replica | about 3 €/month with demo use | 20 € |

At the client's volume, 1,500 invoices and 3,000 pages a month, the estimate is about 38 €/month, about 0.025 € per invoice,
against 3 to 8 € of manual work. Prices and the breakdown are in [`docs/cost.md`](docs/cost.md); the estimate is compared with
Cost Management per environment after the release.

## Well-Architected design

| Pillar | Applied | Trade-off accepted |
|---|---|---|
| Reliability | one queue with a dead-letter queue, retries with `Retry-After`, an idempotent consumer, checkpoints, probes, point-in-time restore drilled | no zone redundancy; cold DR |
| Security | managed identities, local auth off, built-in sign-in with app roles, Prompt Shields, pinned dependencies and actions | no private endpoints, WAF or Defender plans |
| Cost | scale to zero, serverless Cosmos DB, Service Bus Basic, `max_tokens`, file and batch limits, budgets per environment | one business-hours replica in production for REQ-11 |
| Operational excellence | Bicep with `what-if`, one image deployed by digest, canary release with rollback, KPI workbook | one operator |
| Performance | KEDA on HTTP and queue, clients built once, vendor master cached | the app in `spaincentral`, the data in `swedencentral` |

## Deploy

Deployment runs only through GitHub Actions: a merge to `main` deploys staging, and a published release
(`gh release create vX.Y.Z`) deploys production after the author approves the `production` environment. Prerequisites: the
shared base (Foundry account and project with `gpt-5-mini`, Container Registry, Log Analytics) and two empty resource groups.

### Bootstrap

`infra/main.bicep` deploys each environment at resource-group scope with `main.staging.bicepparam` or
`main.production.bicepparam`, which read the image digest, the sign-in client id and the revision suffix from the workflow.

### Federated credentials

One Entra application per environment for the CI principal, with federated credentials for the `staging` and `production`
GitHub environments and for pull requests; no client secret anywhere.

### GitHub secrets and variables

Secrets `AZURE_CLIENT_ID` per environment, `AZURE_CLIENT_ID_PR`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and
`ALERT_EMAIL_ADDRESS`; variables `ACR_NAME`, `SHARED_RESOURCE_GROUP`, `FOUNDRY_ACCOUNT_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`,
`FOUNDRY_MODEL`, and per environment `AUTH_CLIENT_ID`, `RESOURCE_GROUP` and `CONTAINER_APP_NAME`.

### Identities

The CI principals hold Contributor and a Role Based Access Control Administrator role limited to the roles the Bicep assigns.
The app's identity holds data roles on its own Cosmos DB, storage and queue and Cognitive Services User on the shared
account; the scale rule uses a second identity the code cannot use. Sign-in uses one app registration per environment with
the roles `Invoice.Process` and `Invoice.Approve`, assignment required.

## Documentation

- [`docs/PRODUCT.md`](docs/PRODUCT.md): client, process as-is and to-be, requirements with acceptance criteria, KPIs, SLOs and
  the ERP export layout.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md): promotion, rollback, urgent patch, restore, alerts, incidents, load tests.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) and [`docs/RESPONSIBLE_AI.md`](docs/RESPONSIBLE_AI.md).
- [`docs/evaluation.md`](docs/evaluation.md): the evaluation gate, its datasets and results, and experiment 001.
- [`docs/cost.md`](docs/cost.md) and [`docs/adr/`](docs/adr/), ADR-001 to ADR-013.
- [`CHANGELOG.md`](CHANGELOG.md) and the [latest release](https://github.com/Rodrigo-GomezdelMoral/product-finance-folium/releases/latest).

## Author

**Rodrigo Martín Gómez del Moral Herranz**

<a href="https://github.com/Rodrigo-GomezdelMoral"><img src="docs/images/author/github.png" alt="GitHub" height="36"></a>&nbsp;&nbsp;<a href="https://www.linkedin.com/in/rodrigo-mart%C3%ADn-g%C3%B3mez-del-moral-herranz"><img src="docs/images/author/linkedin.png" alt="LinkedIn" height="36"></a>&nbsp;&nbsp;<a href="https://rodrigogomezdelmoralherranz.es"><img src="docs/images/author/portfolio.png" alt="Portfolio" height="36"></a>
