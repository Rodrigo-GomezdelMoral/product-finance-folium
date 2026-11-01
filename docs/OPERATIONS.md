# Operations

How Folium is promoted, watched, restored and paid for. Status on 2026-11-01: staging is deployed through `deploy.yml`
and was used live through the API and the web; the first load test, the cold start, the restore drill and the Advisor review
are recorded below. The first load test did not meet REQ-10 or REQ-11, so nothing is promoted yet.

## Environments and promotion

| | Staging | Production |
|---|---|---|
| Resource group | `rg-folium-stg-swc` | `rg-folium-prod-swc` |
| App, in `spaincentral` (ADR-013) | `ca-folium-stg` in `cae-folium-stg-spc`, 0 to 2 replicas | `ca-folium-prod` in `cae-folium-prod-spc`, 0 to 3 replicas |
| Data | `cosmos-folium-stg-swc`, `stfoliumstgswc`, `sb-folium-stg-swc` | `cosmos-folium-prod-swc`, `stfoliumprodswc`, `sb-folium-prod-swc` |
| Telemetry | `appi-folium-stg-swc`, workbook | `appi-folium-prod-swc`, workbook, `ag-folium-prod-swc` and four alerts |
| Changed by | `deploy.yml`, on every merge to `main` | `release.yml`, on a published release, after the author's approval |

The resource groups, data and telemetry are in `swedencentral`. The app runs in `spaincentral` because the subscription's
one Container Apps environment in `swedencentral` is taken. An outage in either region stops the service (ADR-013).

- **Every merge** builds one image on the runner, tagged `<yyyymmdd>-main-<sha7>`, pushes it to `craiplatformshared`, and
  `deploy.yml` deploys its digest to staging: `what-if`, then a new revision at 0 % behind the `canary` label, a health check
  on that label, 100 % of traffic, the previous revision deactivated, and a smoke test through the API as the staging CI
  principal (`/healthz`, `/api/me`, `/api/invoices`).
- **A release** `vX.Y.Z`: job `verify` (no Azure) checks that the tag's commit has a successful `deploy.yml` run and a
  `load-test` commit status of `success`. Job `promote` (environment `production`, the author approves) resolves the commit's
  image tag to the same digest staging received, deploys it at 0 %, checks health on the label, sends 10 %, reads the new
  revision's server errors (Azure Monitor `Requests`, filtered by revision and `5xx`) every two minutes for ten minutes, then
  sends 100 % and deactivates the old revision, or rolls back and fails.
- **Nothing is rebuilt per environment.** The digest in production is the digest that ran in staging.

## Rollback

- **Production:** run `release.yml` from `main` with `workflow_dispatch` and an earlier release tag. It checks out that tag's
  commit, so the infrastructure and the image match, and promotes its digest with the same canary.
- **Staging:** run `deploy.yml` with `workflow_dispatch` and an image tag (`<yyyymmdd>-main-<sha7>`); it deploys that digest
  without building.
- **Fastest path:** an earlier revision is kept inactive (up to five).
  `az containerapp revision activate` and `az containerapp ingress traffic set --revision-weight <old>=100 <new>=0` restore it
  in about a minute; the next release brings the Bicep back in line.

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
- **Remove an environment:** delete its resource group's resources; the shared base is untouched.

## Model lifecycle

`gpt-5-mini` `2025-08-07` is pinned with `NoAutoUpgrade` and retires on 2027-02-09. By December 2026: evaluate the successor
with the full suite against the baseline, change `FOUNDRY_MODEL` in the Bicep through a PR (the gate runs), release.

## DORA metrics

Read from GitHub Actions runs (`gh run list --workflow <file> --json conclusion,createdAt,updatedAt,headSha`):
deployment frequency (successful `release.yml` runs a week), lead time for changes (merge commit to the end of the successful
`deploy.yml` run, and to production for releases), change failure rate (`release.yml` runs that rolled back over all
releases) and time to restore (from a failed or rolled-back release to the next successful one). Measured from phase 7.

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

| Date | Scenario | p50 | p95 | p99 | Requests/s | Errors | Users | Queue | Replicas | CPU | Memory |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-01 | normal, doubles | 15 s (1 invoice) | | | 0.13 | 24 of 25 uploads `503` | 5 | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 2026-11-01 | peak, doubles | 36 s | 56 s | 56 s | 3.47 | 0 | 60 invoices in 3 batches | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 2026-11-01 | soak 30 min, doubles | 14 s | 31 s | 73 s | 0.70 | 15 of 150 uploads `503`, 1 invoice failed | 5 | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 2026-11-01 | stress, doubles | 16 s | 20 s | 20 s | 3.70 | 3 of 110 uploads `503` | ramp, 10 a minute | 16 | 2 | 0.13 vCPU | 0.52 GB |
| 2026-11-01 | 20 invoices, real services | 56 s | 64 s | 64 s | 2.44 | 0 | 1 batch | | 1 to 2 | | |

**Verdict, 2026-11-01: not promoted.** Over normal, peak and soak, Application Insights gives a p95 of `invoice_ready` of
41.4 s on standard invoices (REQ-11: under 30 s) and an availability of 98.2 % (REQ-10: 99.5 %); two messages were
dead-lettered. The workflow set `load-test` to `failure` on the tested commit. Causes found:

- **The `503`s in the console log came from one defect:** the upload route shared one Service Bus sender, and concurrent first sends raced while
  the AMQP link opened (`'NoneType' object has no attribute 'client_ready_async'` in the console log). Sends are now
  serialised behind a lock with a 30 s timeout; the link stays shared. The next run of the load test is the proof.
- **Capacity under batches:** with four receivers per replica and two replicas, a 20-invoice batch runs in rounds of about
  12 s on the doubles and 13 to 15 s on the real services, and the duplicate check makes each invoice wait for earlier
  uploads still queued or processing. CPU never passed 0.13 of 0.5 vCPU. The author's decision (2026-11-01): ten receivers per replica in
  both environments, the queue rule at ten messages per replica (ADR-003), and the business-hours replica in production
  (ADR-011). The load test runs again after it.
- **The status check read only the first value** of the query's row (`az ... -o tsv` prints one value per line); it now joins
  them, so availability and the invoice count reach the gate.

## Cold start

Measured on 2026-11-01 with staging at zero replicas (ADR-011): the first upload was answered after **35.3 s** (15 s of
platform scheduling, 1.5 s to create the container, 13 s until the second startup probe, about 6 s not broken down) and its invoice was ready 13.3 s
later, about **49 s** from the click. Warm uploads were answered in 2.6 s. `invoice_uploaded` is written after the replica
starts, so REQ-11's metric does not include the cold start.

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
