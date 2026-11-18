# Architecture

Folium turns a supplier invoice into a validated, reviewed and traceable entry for the ERP, exported exactly once. This page
shows what runs where, how an invoice flows from upload to export, which identity holds which role, and how a change reaches
production. The product, its requirements and its SLAs are in [PRODUCT.md](PRODUCT.md); the decisions are in [adr/](adr/).

## Components

![Per environment, the accounts payable team reaches the Folium app, API and worker, which writes Cosmos DB for the audit, Blob Storage write-once and Service Bus, and sends telemetry to Application Insights; with its managed identity it calls the shared platform: Foundry, Document Intelligence, the registry and Log Analytics](images/architecture.svg)

`<env>` is `stg` or `prod`. Every resource below is declared once in `infra/main.bicep` and deployed per environment with its
own parameter file; the shared base is only referenced.

| Component | What it does | Defined in |
|---|---|---|
| Container App `ca-folium-<env>`, `italynorth` | One container, 0.5 vCPU and 1 GiB, on the Consumption profile: the FastAPI API, the built React web from the same origin and the queue consumer, ten receivers per replica. Multiple revisions, five inactive ones kept; probes on `/healthz`, which fails when a consumer stops | `infra/modules/app.bicep`, `Dockerfile`, `app/main.py`, ADR-003, ADR-005 |
| Scale rules | 0 to 2 replicas in staging and 0 to 3 in production: HTTP at 20 concurrent requests and the queue at 10 messages; production also keeps one replica Monday to Friday, 08:00 to 19:00 Madrid time | `app.bicep`, the parameter files, ADR-011 |
| Built-in authentication | Signs users in with Entra ID, with no client secret, and passes `X-MS-CLIENT-PRINCIPAL`; every path redirects to sign-in except `/healthz`; HTTPS only | `app.bicep` (`authConfigs`), ADR-009 |
| Workflow and agents | One graph per invoice: `extract`, `shield`, `normalize`, `validate`, `dedupe`, `review`. One normaliser agent and one read-only assistant on `gpt-5-mini`, in code and self-hosted in the app | `app/workflow.py`, `app/agents.py`, ADR-001, ADR-002, ADR-012 |
| Container Apps environment `cae-folium-env`, `italynorth` | Consumption profile, no zone redundancy, logs to the shared workspace through a diagnostic setting. One for the product: production's deployment creates it and staging's app joins it | `infra/modules/environment.bicep`, ADR-013 |
| Cosmos DB for NoSQL `cosmos-folium-<env>-swc`, `swedencentral` | Serverless, session consistency, continuous 7-day backup, local authentication off. Database `folium`: `invoices`, `audit`, `vendors`, `exports`, `conversations` and `checkpoints` | `infra/modules/data.bicep`, ADR-004 |
| Blob Storage `stfolium<env>swc`, `swedencentral` | Hot, locally redundant: `originals`, written once, and `exports`. Versioning and 7-day soft delete; cool after 30 days, export files deleted after 365 days; shared key and public access off | `data.bicep`, ADR-010 |
| Service Bus Basic `sb-folium-<env>-swc`, `swedencentral` | Queue `invoices`: peek-lock of one minute, five deliveries and then the dead-letter queue, 14-day time to live; local authentication off | `data.bicep`, ADR-003 |
| Application Insights `appi-folium-<env>-swc`, `swedencentral` | On the shared workspace, with Entra-authenticated ingestion: requests, dependencies, the KPI events and the workbook *Folium KPIs, SLAs and health* | `infra/modules/monitor.bicep`, `app/telemetry.py` |
| Alerts, production only | Action group `ag-folium-prod-swc`; three log alerts (business-hours availability, p95 ready time, server errors), read every 15 minutes over the last hour, and one metric alert on dead-lettered messages | `monitor.bicep` |
| Budget `budget-folium-<env>` | 10 € a month in staging and 20 € in production, with e-mails at 50, 80 and 100 % of actual cost | `monitor.bicep`, the parameter files |
| Shared base, `swedencentral`, read only | In `rg-aiplatform-shared-swc`: registry `craiplatformshared`, Foundry account `fdry-aiplatform-shared-swc` (`gpt-5-mini`, Document Intelligence, Prompt Shields) with its project `proj-aiplatform-shared`, and Log Analytics `log-aiplatform-shared-swc`. Folium's Bicep adds role assignments there and changes nothing else | `infra/main.bicep` (`existing`), `infra/modules/shared.bicep`, ADR-007 |

The apps run in `italynorth` and everything that holds data in `swedencentral`, both in the EU, because the subscription allows
one Container Apps environment per region and its `swedencentral` slot was taken (ADR-013); an outage in either region stops
the service. `gpt-5-mini` is a Global deployment and may process outside the EU, so the IBAN never reaches it (ADR-008).
Nothing is zone redundant and there is no standby region: recovery is a redeploy and a point-in-time restore
([OPERATIONS.md](OPERATIONS.md#restore-rpo-15-minutes-rto-4-hours)).

![Production's resource group as deployed, in the Azure portal: the container app and the Container Apps environment in Italy North; Cosmos DB, the app's and the scale rule's managed identities, Service Bus and the storage account in Sweden Central; and the Failure Anomalies smart detector, 8 of its 15 resources](images/resource-group-prod.png)

The Failure Anomalies smart detector is created by Application Insights on its own; the Bicep does not declare it.

## An invoice, end to end

![The workflow per invoice: upload, extract with Document Intelligence, shield with Prompt Shields, normalise with the one agent, validate, review by a person and export; a flagged attack skips the normaliser and goes to validation, and checkpoints from extraction to review let any replica resume it](images/workflow.svg)

1. **Sign-in.** The platform signs the user in and sets the principal header; the API reads the app roles from it and answers
   401 without the header and 403 without the role ([roles](PRODUCT.md#roles)).
2. **Upload.** `POST /api/invoices` takes up to 20 files of 10 MB (413 beyond that), PDF, JPEG or PNG by their first bytes
   (415 otherwise). Each original is written once to `originals` with its SHA-256, the invoice is created as `queued` in
   Cosmos DB with the first entry of its timeline, and one Service Bus message carries only the invoice id. The API answers 202;
   if the queue is unavailable, the invoices are marked `failed` and the answer is 503 with `Retry-After`.
3. **Processing.** A consumer takes the message under peek-lock, claims the invoice from `queued` to `processing` with its ETag,
   so one replica of one revision works on it, and runs the workflow. `extract` reads the original with Document Intelligence
   `prebuilt-invoice` and keeps each field's confidence and page. `shield` sends the extracted text to Prompt Shields: a
   detected attack adds a `possible_injection` finding and skips the normaliser. `normalize` lets the normaliser fill only the
   tax lines and the IRPF withholding, with the IBAN masked, and rejects any amount not printed in the document. `validate` runs
   the tax and arithmetic rules and matches the vendor against the vendor master read at start-up. `dedupe` looks for exact
   and probable duplicates.
4. **Ready for review.** `review` pauses the workflow with a review request, `ready` with no finding and `with_lead` with any,
   and its checkpoints stay in the `checkpoints` container. The event `invoice_ready` carries the seconds since the upload,
   which is REQ-11's measure. An error returns the message to the queue; on the fifth delivery the invoice is marked `failed`
   with the error type and the message is dead-lettered.
5. **Review.** `POST /api/invoices/{id}/review` checks the caller and that the invoice is waiting, then resumes the workflow
   from the checkpoint that holds the stored request id, on any replica. Corrections are recorded with the value before and
   after, who and when. A clerk's approval closes an invoice with no open finding; anything else goes to the lead, who
   approves or rejects with a reason. The save carries the ETag, so of two decisions racing only one is kept.
6. **Export.** `POST /api/exports`, for the lead only, needs an `Idempotency-Key`: the batch id derives from it, the batch is
   created once, every approved invoice becomes `exported`, and the CSV and JSON files in the
   [ERP layout](PRODUCT.md#erp-export-layout) are written to the `exports` blob container. The same key returns the same
   batch, and an exported invoice never enters a later one.
7. **Trace.** Every step, correction and decision is a timeline entry, copied once to the `audit` container with the model
   and prompt versions; the original is streamed through the API, never through a SAS link.

The assistant is outside this path: `POST /api/chat` streams its answer, which it builds with two read-only tools,
`find_invoices` and `get_invoice`, that never return the IBAN, and its history is kept in the `conversations` container. The
events `invoice_uploaded`, `invoice_ready`, `field_corrected`, `invoice_approved`, `invoice_exported` and `feedback` feed the
KPI and SLA tiles of the workbook and the production alerts.

## Identities

Every call from the app to an Azure service is authenticated with Entra ID: local authentication is off on Cosmos DB, Storage,
Service Bus and Application Insights, and keys exist only for the local emulators.

| Identity | Created by | Roles |
|---|---|---|
| `id-folium-<env>`, user-assigned, the app's | `infra/main.bicep` | Own environment: Cosmos DB Built-in Data Contributor on the database `folium`, Storage Blob Data Contributor on the storage account, Azure Service Bus Data Sender and Data Receiver on the queue `invoices`, Monitoring Metrics Publisher on Application Insights. Shared base: AcrPull on the registry, Cognitive Services User on the Foundry account, Foundry User on the project |
| `id-folium-<env>-scale`, user-assigned | `infra/main.bicep` | Azure Service Bus Data Owner on the queue `invoices` only, for the queue scale rule; attached with `lifecycle: None`, so the code cannot obtain its tokens (ADR-006) |
| CI principals, one Entra application per environment | The author's scripts, outside this repository | Federated credentials for the `staging` and `production` GitHub environments and for pull requests, no client secret. Contributor and a Role Based Access Control Administrator role limited to the roles the Bicep assigns; a custom role for the nested deployment in the shared group (ADR-007). Staging's pushes the image, may join `cae-folium-env` but not change it (ADR-013), and holds `Invoice.Process` for the smoke test and the load test (ADR-009). Both also hold Log Analytics Contributor on the shared workspace, an open item in [Known limitations](OPERATIONS.md#known-limitations) |
| `folium-<env>`, the sign-in app registration | The author's scripts, outside this repository | App roles `Invoice.Process` (clerk) and `Invoice.Approve` (lead), assignment required (ADR-009) |
| The operator | The author's scripts, outside this repository | No standing data role in production: its vendor master was seeded once with a temporary role, removed afterwards ([OPERATIONS.md](OPERATIONS.md#production-vendor-master)) |

## Environments and promotion

Local runs on the emulators of `ops/compose.yaml`. Staging (`rg-folium-stg-swc`) and production (`rg-folium-prod-swc`) are
separate resource groups, each with its own app, data, identities, telemetry and budget; they share the Container Apps
environment (ADR-013) and the shared base (ADR-007).

| | Staging | Production |
|---|---|---|
| Container Apps environment, `italynorth` | Joins `cae-folium-env` | Owns `cae-folium-env`, in `rg-folium-prod-swc` |
| App, `italynorth` | `ca-folium-stg`, 0 to 2 replicas | `ca-folium-prod`, 0 to 3 replicas, one warm in business hours |
| Data, identities, telemetry, `swedencentral` | Its own, with the workbook | Its own, with the workbook, the action group and four alerts |
| Changed by | `deploy.yml`, on every merge to `main` | `release.yml`, on a published release, after the author's approval |

![Local code with emulators merges to staging, where the API scales to zero; after the load test and the author's approval, a release deploys the same image to production as a 10 % canary; the Container Apps environment, the registry with one image and Foundry are shared](images/environments.svg)

- **Pull request.** `ci.yml` runs lint, format, types, tests and the code budget, the web build with keyboard-only flows and
  axe, and the Bicep build and lint; `eval.yml` runs the evaluation smoke suite when the agents, the prompts or the workflow
  change ([evaluation.md](evaluation.md)).
- **Build once.** On every merge, `deploy.yml` builds the image on the runner, tags it `<yyyymmdd>-main-<sha7>`, pushes it and
  deploys its digest to staging: `what-if`, a new revision at 0 % behind the `canary` label, a health check on that label,
  100 % of traffic, the previous revision deactivated, and a smoke test through the API.
- **Load test.** `load-test.yml`, dispatched from `main`, redeploys the staging digest as a revision where Document
  Intelligence and the model are doubles, runs normal, peak, soak and stress with Locust, restores the stable revision, sends
  20 invoices through the real services and sets the `load-test` status on the tested commit from REQ-10 and REQ-11.
- **Release gate.** `release.yml` refuses a tag whose commit has no successful merge deployment or no successful `load-test`
  status; the load test is not required when only `web/`, `docs/`, `.github/` or Markdown files changed since the last
  release that reached production (ADR-014). Then it waits for the author's approval of the `production` environment.
- **Canary.** The release deploys the digest staging received as a new revision at 0 %, checks its health on the `canary`
  label, sends it 10 % of the traffic for ten minutes while reading its server errors every two minutes, then sends 100 % and
  deactivates the previous revision, or rolls back and fails.
- **Rollback.** `release.yml` dispatched with an earlier tag, from `v1.0.1` on; in staging, `deploy.yml` dispatched with an
  earlier image tag; or one of the inactive revisions, activated again ([OPERATIONS.md](OPERATIONS.md#rollback)).
- **Demo.** `pages.yml` publishes the recorded demo to GitHub Pages when `web/` changes; it has no backend.
