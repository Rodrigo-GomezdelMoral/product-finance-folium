# Operations

How Folium is promoted, watched, restored and paid for. Status on 2026-11-03: `v1.0.0` stopped before production, because
creating its regional Container Apps environment hit the subscription's limit; `v1.0.1` was the first release in production,
and `v1.0.2` and `v1.0.3` followed, each promoted by `release.yml` after the author's approval. Staging is deployed on every
merge and was used live through the API and the web. Production has served only health probes so far (1,891 `GET /healthz`
and no KPI event in 30 days), and its vendor master must be seeded before the first invoice (below). The load tests, cold
starts, restore drill, DORA figures and Advisor reviews are recorded below, and the known limitations close this file.

## Environments and promotion

| | Staging | Production |
|---|---|---|
| Resource group | `rg-folium-stg-swc` | `rg-folium-prod-swc` |
| App, in `italynorth` (ADR-013) | `ca-folium-stg`, 0 to 2 replicas | `ca-folium-prod`, 0 to 3 replicas |
| Container Apps environment | joins `cae-folium-env` | owns `cae-folium-env`, in `rg-folium-prod-swc` |
| Data | `cosmos-folium-stg-swc`, `stfoliumstgswc`, `sb-folium-stg-swc` | `cosmos-folium-prod-swc`, `stfoliumprodswc`, `sb-folium-prod-swc` |
| Telemetry | `appi-folium-stg-swc`, workbook | `appi-folium-prod-swc`, workbook, `ag-folium-prod-swc` and four alerts |
| Changed by | `deploy.yml`, on every merge to `main` | `release.yml`, on a published release, after the author's approval |

The resource groups, data and telemetry are in `swedencentral`. The subscription allows 5 Container Apps environments in
all and 1 per region, so Folium has one, `cae-folium-env` in `italynorth`: the production deployment creates and changes
it, and the staging app joins it with read and join rights only. An outage in either region stops the service (ADR-013).

- **Every merge** builds one image on the runner, tagged `<yyyymmdd>-main-<sha7>`, pushes it to `craiplatformshared`, and
  `deploy.yml` deploys its digest to staging: `what-if`, then a new revision at 0 % behind the `canary` label, a health check
  on that label, 100 % of traffic, the previous revision deactivated, and a smoke test through the API as the staging CI
  principal (`/healthz`, `/api/me`, `/api/invoices`).
- **A release** `vX.Y.Z`: job `verify` (no Azure) checks that the tag's commit has a successful `deploy.yml` run and a
  `load-test` commit status of `success`. The load test is not required when every path changed since the last release that reached
  production (published, with a successful `release.yml` run) matches `web/**`, `docs/**`, `.github/**` or `*.md`; the job prints each changed path and the decision, and with no
  such release the load test is required (ADR-014). Job `promote` (environment `production`, the author approves) resolves the commit's
  image tag to the same digest staging received, deploys it at 0 %, checks health on the label, sends 10 %, reads the new
  revision's server errors (Azure Monitor `Requests`, filtered by revision and `5xx`) every two minutes for ten minutes, then
  sends 100 % and deactivates the old revision, or rolls back and fails.
- **Nothing is rebuilt per environment.** The digest in production is the digest that ran in staging.
- **Which revision served a request:** the Azure Monitor `Requests` metric of the app split by `revisionName`, as the canary
  reads it. From `v1.0.4` on, Application Insights also names the app in `cloud_RoleName` and the serving revision in
  `application_Version` (`OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`, set per revision by `infra/modules/app.bicep`);
  `cloud_RoleInstance` is a replica, not a revision.

## Production vendor master

The app reads the `vendors` container once at start-up and matches every invoice against it (REQ-03); with an empty master,
every invoice gets an `unknown_vendor` finding and goes to the lead. Staging was seeded by the operator with `ops/seed.py`
(40 vendors from `data/vendors.json`). Production has no human data role by design, so the author seeds it once with a script
outside this repository: a temporary Cosmos DB Built-in Data Contributor role for the operator on `cosmos-folium-prod-swc`,
`python -m ops.seed` with the app's own `COSMOS_ENDPOINT`, `STORAGE` and `SERVICEBUS` values kept in shell variables, the
role removed, and the `DocumentCount` metric of `vendors` read back at 40. Seed before a release; after one, restart the
active revision (`az containerapp revision restart`) so its replica reads the seeded master. On 2026-11-03 every production
container holds 0 documents.

## Rollback

- **Production:** run `release.yml` from `main` with `workflow_dispatch` and an earlier release tag. It checks out that tag's
  commit, so the infrastructure and the image match, and promotes its digest with the same canary. `v1.0.0` is never a
  target: its Bicep creates a regional environment of its own for production instead of `cae-folium-env` (ADR-013), which
  is how its release failed; the earliest target is `v1.0.1`.
- **Staging:** run `deploy.yml` with `workflow_dispatch` and an image tag (`<yyyymmdd>-main-<sha7>`); it deploys that digest
  without building.
- **Fastest path:** an earlier revision is kept inactive (up to five).
  `az containerapp revision activate` and `az containerapp ingress traffic set --revision-weight <old>=100 <new>=0` restore it
  without a deployment; the next release brings the Bicep back in line. Its time, cold start included, is not measured yet:
  the rollback drill after `v1.0.4` records it.

## Urgent patch

Pre-approved path: a short branch from `main`, a PR with CI green, merge (staging deploys), `load-test.yml` with
`soak_minutes` 5 instead of 30, then a patch release `vX.Y.Z+1` and its approval. Nothing skips staging.

## Restore (RPO 15 minutes, RTO 4 hours)

- **Cosmos DB:** continuous backup, 7-day tier. Restore to a new account at a point in time:
  `az cosmosdb restore -g <rg> --account-name cosmos-folium-<env>-swc --target-database-account-name <new> --restore-timestamp <UTC> --location swedencentral`,
  give the app identity the Data Contributor SQL role on it, and point `COSMOS_ENDPOINT` at it (or copy the affected
  containers back).
- **Blobs:** versions and 7-day soft delete: `az storage blob undelete` or promote a previous version.
- **Drill, staging, 2026-11-01:** Cosmos DB restored to a new account (`cosmos-folium-stg-restore`) at a point six minutes
  back, while a load test was writing: **656 s (11 min)** from request to a usable account. The restored containers held
  exactly the data of that moment (7 invoices, 40 vendors, 1 export, 65 audit entries, read from the `DocumentCount` metric),
  against 97 invoices in the live account by then. Data-plane role assignments are not restored: the app identity and the
  operator need the Data Contributor SQL role again on the new account, which is an identity change for the author. A blob
  deleted from `originals` was restored from its previous version in **13 s** with the same SHA-256. Measured RTO for the data:
  under 15 minutes, plus the role assignment and the `COSMOS_ENDPOINT` change; the 4-hour RTO and 15-minute RPO hold. The
  restored account was deleted after the check.

## Alerts (production only)

All go to the author by e-mail through `ag-folium-prod-swc`. Log alerts run every 15 minutes over the last hour.

| Alert | Fires when | Kind |
|---|---|---|
| `alert-folium-availability` | business-hours availability below the 99.7 % SLO (at least 20 requests) | log |
| `alert-folium-ready-p95` | p95 time to ready of standard invoices above the 25 s SLO (at least 5 invoices) | log |
| `alert-folium-errors` | server errors above 1 % of requests (at least 20 requests) | log |
| `alert-folium-dead-letters` | any dead-lettered message on the namespace | metric |
| `budget-folium-<env>` | actual cost at 50, 80 and 100 % of the month's budget | budget, both environments |

## Incidents

The author is the only operator, so every role is the author's; the order matters.

1. **Acknowledge** the e-mail and open the workbook *Folium KPIs, SLAs and health* of the environment.
2. **Locate:** the health model shows dependency failures by target (Document Intelligence, model, Prompt Shields, Cosmos DB,
   Service Bus, Storage) and server errors by hour; console and system logs are in `log-aiplatform-shared-swc`.
3. **Mitigate:** a bad release is rolled back (above); a dependency outage needs no action, because uploads wait in the queue
   and are retried five times, then marked `failed` with the error type; a 429 from the model leaves the deterministic mapping
   and a finding.
4. **Recover:** after the cause is fixed, the clerk uploads the failed invoices again; dead-lettered messages are inspected in
   the portal's Service Bus Explorer.
5. **Learn:** a short note in this file with the timeline, the cause and the change that prevents it (SE:12, OE:08).

## Start, stop and zero

- **At rest** staging scales to zero by itself (minimum 0 replicas); production keeps one replica Monday to Friday from
  08:00 to 19:00 (Europe/Madrid) through the `business-hours` cron rule (ADR-011, about 3 to 4 €/month) and scales to zero
  outside them; check with
  `az containerapp replica list -n ca-folium-<env> -g <rg> --revision <revision>`. Staging ends every phase at zero.
- **Pause production without deleting:** disable the three log alerts (`az monitor scheduled-query update --disabled true`)
  and the deploying workflows (`gh workflow disable deploy.yml`, `release.yml`, `load-test.yml`). What still bills: Cosmos DB
  and blob storage (cents), and the business-hours replica; to stop it too, `az containerapp revision deactivate` the active revision.
- **Staging at zero or removed** never touches production: stop or delete `ca-folium-stg` and the resources of
  `rg-folium-stg-swc`; `cae-folium-env` is in `rg-folium-prod-swc` and stays.
- **Remove production:** deleting the resources of `rg-folium-prod-swc` also deletes `cae-folium-env` and stops staging
  until the environment is recreated. The shared base is untouched.
- **Recreate the environment:** run `../_scripts/product-finance-folium/06-environment.sh`, which deletes the first
  decision's `cae-folium-stg-spc` and its app if present, deploys `infra/modules/environment.bicep` with production's
  parameters and grants the staging CI principal its join role again; then deploy staging (`deploy.yml`) and production (`release.yml`) and run `04-signin.sh`
  after each, because the apps' host names change. To move region, change `environmentLocation` and the script's
  `LOCATION` together; while the subscription holds 5 environments, the old one must be deleted first.

## Model lifecycle

`gpt-5-mini` `2025-08-07` is pinned with `NoAutoUpgrade` and retires on **2027-07-13** (Microsoft Learn, *Model retirement
schedule*, read on 2026-11-02; the account's `az cognitiveservices account list-models` `deprecation.inference`, read on
2026-11-03). With `NoAutoUpgrade` the deployment stops answering at retirement instead of moving to the replacement.
Microsoft names the official replacement about 90 to 120 days before retirement, so between mid-March and mid-April 2027,
and sends a retirement notice at least 60 days before (Learn, *Foundry Models lifecycle and support policy*). Plan: by the
end of April 2027, evaluate the named replacement with the full suite against the baseline (candidates may be tried earlier),
change `FOUNDRY_MODEL` in the Bicep through a PR (the gate runs), and release by the end of May 2027, six weeks before
retirement.

## DORA metrics

Read from GitHub Actions runs (`gh run list --workflow <file> --json conclusion,createdAt,updatedAt,headSha`):
deployment frequency (successful `release.yml` runs a week), lead time for changes (merge commit to the end of the successful
`deploy.yml` run, and to production for releases), change failure rate (`release.yml` runs that rolled back over all
releases) and time to restore (from a failed or rolled-back release to the next successful one). Read on 2026-11-03:

| Metric | Value |
|---|---|
| Deployment frequency, production | 3 successful releases in two days: `v1.0.1` and `v1.0.2` on 2026-11-02, `v1.0.3` on 2026-11-03 |
| Lead time, merge to production | `v1.0.1` 1 h 23 min, `v1.0.2` 20 min, `v1.0.3` 20 min, each with the approval and the ten-minute canary |
| Lead time, merge to staging | 3.5 to 4.5 minutes over the last four merges |
| Change failure rate | 1 of 4 release runs (25 %): `v1.0.0` failed in `promote` before production, with no production impact |
| Time to restore | 9 h 46 min, from the `v1.0.0` failure to the `v1.0.1` success |
| Staging deployments | 10 `deploy.yml` runs on merges, 2 failed (2026-10-31) |

## Load tests

`load-test.yml`, manual, from `main`, environment `staging`: the staging digest is redeployed as a revision with
`DOUBLES=load` and made the only active one, then **normal** (5 users, one invoice a minute each, 5 minutes), **peak** (three
20-invoice batches in 2 minutes), **soak** (normal rate, 30 minutes) and **stress** (ramp until p95 passes 30 s or errors pass
1 %); the stable revision is restored and **20 invoices go through the real services**. REQ-10 and REQ-11 are read from
Application Insights over normal, peak and soak; if both hold, the workflow sets the `load-test` commit status to `success`.
Results, with date, go below. Dispatch it only with no deployment queued: it shares the `staging` concurrency
group with `deploy.yml`, and a newer pending run cancels an older pending one.

p50, p95 and p99 are Locust's `READY invoice` entries: from the upload until the web would show the review card. Queue,
replicas, CPU and memory are maxima over the whole run on the doubles.

| Run | Scenario | p50 | p95 | p99 | Requests/s | Errors | Users | Queue | Replicas | CPU | Memory |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3, 2026-11-02 | normal, doubles | 16 s | 29 s | 29 s | 0.84 | 0 of 25 uploads | 5 | 25 | 2 | 0.20 vCPU | 0.49 GB |
| 3, 2026-11-02 | peak, doubles | 27 s | 40 s | 41 s | 2.70 | 0 | 60 invoices in 3 batches | 25 | 2 | 0.20 vCPU | 0.49 GB |
| 3, 2026-11-02 | soak 30 min, doubles | 16 s | 17 s | 17 s | 0.73 | 0 of 150 uploads | 5 | 25 | 2 | 0.20 vCPU | 0.49 GB |
| 3, 2026-11-02 | stress, doubles | 16 s | 27 s | 30 s | 8.75 | 1 of 5,376 requests (a status read), 0 of 583 uploads | ramp, 10 a minute, stopped at about 100 | 25 | 2 | 0.20 vCPU | 0.49 GB |
| 3, 2026-11-02 | 20 invoices, real services | 46 s | 51 s | 51 s | 2.02 | 0 | 1 batch | | | | |
| 2, 2026-11-01 | normal, doubles | 16 s | 30 s (max 29.6 s) | 30 s | 0.83 | 0 of 25 uploads | 5 | 22 | 2 | 0.18 vCPU | 0.49 GB |
| 2, 2026-11-01 | peak, doubles | 27 s | 41 s | 41 s | 2.83 | 0 | 60 invoices in 3 batches | 22 | 2 | 0.18 vCPU | 0.49 GB |
| 2, 2026-11-01 | soak 30 min, doubles | 16 s | 16 s | 17 s | 0.73 | 0 of 150 uploads, no invoice failed | 5 | 22 | 2 | 0.18 vCPU | 0.49 GB |
| 2, 2026-11-01 | stress, doubles | 16 s | 27 s | 29 s | 8.94 | 0 of 616 uploads | ramp, 10 a minute, stopped at about 105 | 22 | 2 | 0.18 vCPU | 0.49 GB |
| 2, 2026-11-01 | 20 invoices, real services | 44 s | 49 s | 49 s | 2.16 | 0 | 1 batch | | 1 to 2 | | |
| 1, 2026-11-01 | normal, doubles | 15 s (1 invoice) | | | 0.13 | 24 of 25 uploads `503` | 5 | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 1, 2026-11-01 | peak, doubles | 36 s | 56 s | 56 s | 3.47 | 0 | 60 invoices in 3 batches | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 1, 2026-11-01 | soak 30 min, doubles | 14 s | 31 s | 73 s | 0.70 | 15 of 150 uploads `503`, 1 invoice failed | 5 | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 1, 2026-11-01 | stress, doubles | 16 s | 20 s | 20 s | 3.70 | 3 of 110 uploads `503` | ramp, 10 a minute | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 1, 2026-11-01 | 20 invoices, real services | 56 s | 64 s | 64 s | 2.44 | 0 | 1 batch | | 1 to 2 | | |

**Run 3 (41494700777, commit `f92f034`, released as `v1.0.1`), on `cae-folium-env`, verdict 2026-11-02: REQ-10 and REQ-11
met.** Over normal, peak and soak, Application Insights gives a p95 of `invoice_ready` of **24.2 s** over 240 invoices and an
availability of **100 %**; the workflow set `load-test` to `success` on the tested commit. These are the figures of the
environment that runs today. One status read failed in stress (1 of 5,376 requests, 0.02 %) and no upload failed; the
dead-letter queue's maximum stayed at run 1's two messages. Peak CPU was 0.20 of 0.5 vCPU, memory under 0.5 GB, two
replicas. The real-services batch's upload was answered after 18 s, because the restored stable revision started from zero.
`v1.0.2` and `v1.0.3` changed only web, document and workflow paths and ran no load test (ADR-014). Both gates measure all
hours of the run, not REQ-10's business-hours window.

Runs 1 and 2 ran on the earlier staging environment, `cae-folium-stg-spc` in `spaincentral`, removed with `v1.0.1`
(ADR-013); they are kept as history.

**Run 2 (41299957986, commit `4785e17`), verdict 2026-11-01: REQ-10 and REQ-11 met, promotable.** Over normal, peak and
soak, Application Insights gives a p95 of `invoice_ready` of **24.2 s** (REQ-11: under 30 s; SLO target under 25 s) and an
availability of **100 %** (REQ-10: 99.5 %). The workflow set `load-test` to `success` on the tested commit. No upload or
request failed in any scenario and no invoice ended `failed`; the dead-letter queue still held run 1's two messages and no
new one. With ten receivers per replica, peak CPU rose from 0.13 to 0.18 of 0.5 vCPU and memory stayed under 0.5 GB.

- **Batches alone are slower than the month.** A month-end batch on its own still has a p95 of 41 s on the doubles (56 s in
  run 1) with staging's two replicas; REQ-11 is a monthly p95, and the mix of normal, peak and soak stays under it.
  Production allows three replicas and keeps one warm in business hours (ADR-011); its p95 alert is the watch.
- **Stress** stopped at about 105 users, about 105 uploads a minute, when the current p95 passed 30 s, with no error.
- **Real services:** the batch's upload was answered after 17 s, because the restored stable revision started from zero;
  REQ-11's metric starts at `invoice_uploaded`, after it, so it sees about 27 to 32 s of the 44 to 49 s measured here.

**Run 1 (41293079362), verdict 2026-11-01: not promoted.** Over normal, peak and soak, Application Insights gave a p95 of
`invoice_ready` of 41.4 s on standard invoices (REQ-11: under 30 s) and an availability of 98.2 % (REQ-10: 99.5 %); two
messages were dead-lettered. The workflow set `load-test` to `failure` on the tested commit. Causes found:

- **The `503`s in the console log came from one defect:** the upload route shared one Service Bus sender, and concurrent first sends raced while
  the AMQP link opened (`'NoneType' object has no attribute 'client_ready_async'` in the console log). Sends are now
  serialised behind a lock with a 30 s timeout; the link stays shared. Run 2 had no failed upload.
- **Capacity under batches:** with four receivers per replica and two replicas, a 20-invoice batch runs in rounds of about
  12 s on the doubles and 13 to 15 s on the real services, and the duplicate check makes each invoice wait for earlier
  uploads still queued or processing. CPU never passed 0.13 of 0.5 vCPU. The author's decision (2026-11-01): ten receivers per replica in
  both environments, the queue rule at ten messages per replica (ADR-003), and the business-hours replica in production
  (ADR-011), measured by run 2.
- **The status check read only the first value** of the query's row (`az ... -o tsv` prints one value per line); it now joins
  them, so availability and the invoice count reach the gate.

## Cold start

Measured on 2026-11-01 with staging at zero replicas (ADR-011): the first upload was answered after **35.3 s** (15 s of
platform scheduling, 1.5 s to create the container, 13 s until the second startup probe, about 6 s not broken down) and its invoice was ready 13.3 s
later, about **49 s** from the click. Warm uploads were answered in 2.6 s. `invoice_uploaded` is written after the replica
starts, so REQ-11's metric does not include the cold start. That measurement was on the earlier staging environment. On
`cae-folium-env`, on 2026-11-02 outside business hours, `/healthz` answered after **34.9 s** in production and **35.8 s** in
staging from zero replicas (one request each).

## Live test in staging

2026-11-01, as the accounting lead, through the API and the web: a batch of six invoices (PDF, scanned PDF, JPEG) ready in 12
to 24 s; an exact duplicate flagged at upload by hash and another by vendor tax ID and number, both sent to the lead and
rejected with a reason; an injected invoice detected by Prompt Shields, with the normaliser skipped and a
`possible_injection` finding; a correction recorded in the timeline and the `field_corrected` event; approval by the lead with
a reason; an export twice with the same `Idempotency-Key` returning the same batch, and a new key finding nothing left to
export; the timeline with the model (`gpt-5-mini-2025-08-07`) and prompt (`normalizer_v2`) versions; the original's SHA-256
matching; `401` without a session. Through the web, an upload showed its review card after 13 s with its findings and the
step times, and the lead's approval left the card in the *Approved* state. The KPI events (`invoice_uploaded`,
`invoice_ready`, `field_corrected`, `invoice_approved`, `invoice_exported`) arrived in Application Insights. One defect
found: the assistant's streamed answer repeated its text, because the Responses API's final text event replaces what the
deltas built; the route now skips replacing contents.

## Azure Advisor

`az advisor recommendation list` at the close of every deploying phase; each recommendation is applied when free or
justified here.

**2026-11-01:** no recommendation on `rg-folium-stg-swc` or `rg-folium-prod-swc`. On the shared base and the subscription:
geo-replication and Premium for `craiplatformshared` (a shared-base tier decision, ADR-007), a second replica for AI Search
(not used by Folium), a newer Azure OpenAI API version on the shared account (Folium calls the Responses API through the
pinned `agent-framework-foundry` 1.15.0), and a Service Health alert at subscription level (free,
but it belongs to the shared base, not to one product). None is Folium's to apply.

**2026-11-02:** staging: zone redundancy for the storage account (High), a higher minimum replica count (Medium) and
Service Bus Premium (Low); production: Service Bus Premium (Low). Minimum replicas: staging scales to zero by design and
production keeps one replica in business hours (ADR-011). Premium: Basic covers one queue at this volume (ADR-003,
`docs/cost.md`). Storage zone redundancy: not applied; the originals are locally redundant with versioning and 7-day soft
delete, the same single-zone trade-off as the environment and Cosmos DB (cold DR, ADR-004, `docs/cost.md`), and no ADR
names the storage account yet.

## Known limitations

Open on 2026-11-03, each with its figure and the reason it stays open.

| Limitation | Figure and date | Reason, and when it is revisited |
|---|---|---|
| No production use yet | 0 KPI events and only `GET /healthz` in production, 2026-11-03 | Production waits for the vendor master seeding and the author's walk-through, which gives the first real requests, KPIs and `feedback` event |
| Requirements proven in staging only | every Must used in staging; none in production, 2026-11-03 | Same cause; the walk-through repeats each Must in production |
| SLA figures from the load-test gate | REQ-10 100 % and REQ-11 24.2 s over all hours of run 3, 2026-11-02. Staging in business hours: 411 requests, 0 errors (2026-11-02, 17:47 to 18:00 UTC only); 30-day staging p95 30.9 s over 2,914 load-test invoices, run 1 included | REQ-10's window needs real business-hours traffic; production's workbook and alerts measure it once there is use |
| The canary watch saw no traffic | `v1.0.2`'s and `v1.0.3`'s ten-minute canaries passed while production served only probes | A canary proves something only with traffic; kept as a gate, the walk-through gives the first |
| Rollback and alert not rehearsed | never run on 2026-11-03; the restore drill ran on 2026-11-01 | Drills after `v1.0.4`, staging first, with the author's approval and the time measured |
| REQ-12 erasure (Should) tested only | `test_erase_redacts_personal_fields` passes; no live erasure | Invoices are kept six years, so the first erasure of a 2026 invoice is possible in 2033; the refusal inside retention is the only live path |
| Cost per invoice estimated, not measured | estimate 0.025 €; month to date on 2026-11-02: staging 0.85 € (Cosmos DB), production 0.006 € (Azure Monitor), no Container Apps charge yet | The Foundry and Document Intelligence spend sits in the shared group and cannot be split per product; compared with Cost Management after a month of use |
| README KPIs from the operator's tests | "6 approvals, 83 %" was true at mid-day on 2026-11-01; by the end of that day 7 approvals, touchless 71.4 % (5 of 7), 2 corrected fields, two approvals scripted | Operator tests, not client use; production's workbook replaces them |
| Node 26 for the web build stage | Dependabot PR #8 (Node 24.22.2 to 26.12.1) closed by the author on 2026-11-02 | The change is in the `Dockerfile`, a runtime path, so it needs a load test, and the stage only builds static files; Node 24 is supported until 2028-04-30. Revisited at the next release that changes the runtime, or by early 2028 at the latest |
| Storage without zone redundancy | Advisor, High, staging, 2026-11-02 | Single-zone trade-off of the whole product (above) |
| CI principals' privileges | the RBAC Administrator condition of both CI principals still allows *Key Vault Secrets User*, although there is no vault (ADR-009); both hold *Log Analytics Contributor* on the shared workspace, justified in no ADR | Identity changes are the author's; narrowed at the next identity review |
| Required checks | the ruleset requires `python` and `evaluate`; `web` (axe) and `bicep` run on every PR but are not required | GitHub settings are the author's |
| Unused variable | `SHARED_RESOURCE_GROUP` is set in GitHub and listed in the README, but no workflow reads it; the shared group is the Bicep default | Harmless; removed with the next workflow change |
| Steps that rely on the author's scripts | recreating the environment and the sign-in redirect (above) call the author's scripts outside this repository | They hold identity and settings changes, which stay the author's |
| Workflow lint | actionlint 1.7.12 gives four shellcheck notes, none an error: two redirect groupings, one unquoted variable, one unused loop variable | Style only; fixed with the next change to those workflows |
| Code budget at its limit | Python 1,450 of 1,450 and tests 700 of 700 lines | Any code fix must be budget-neutral; the author decides any raise |
| Demo details | in demo mode the composer is disabled with a placeholder, cut on mobile; the profile reads "Demo" until a run plays | The demo replays recorded runs only; free text needs the deployed system |
