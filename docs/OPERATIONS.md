# Operations

How Folium is promoted, watched, restored and paid for. Status on 2026-11-10: `v1.0.0` stopped before production, because
creating its regional Container Apps environment hit the subscription's limit; `v1.0.1` was the first release in production,
and `v1.0.2` to `v1.0.5` followed, each promoted by `release.yml` after the author's approval. Since 2026-11-08 staging and
production run `v1.0.5`'s commit, `8d7b7d2`. Staging is deployed on every merge and was used live through the API and the web.
Production's vendor master was seeded on 2026-11-03; every Must was then walked through in production on `v1.0.4` through the
API, and on 2026-11-08 the demo recording used it on `v1.0.5` through the web (below). The load tests, cold starts, restore and
rollback drills, DORA figures and Advisor reviews are recorded below, and the known limitations close this file.

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
active revision (`az containerapp revision restart`) so its replica reads the seeded master. Seeded on 2026-11-03: the
`DocumentCount` metric of `vendors` reads 40, and the temporary role is gone (one Cosmos DB SQL role assignment left in
production, the app's).

## Rollback

- **Production:** run `release.yml` from `main` with `workflow_dispatch` and an earlier release tag. It checks out that tag's
  commit, so the infrastructure and the image match, and promotes its digest with the same canary. `v1.0.0` is never a
  target: its Bicep creates a regional environment of its own for production instead of `cae-folium-env` (ADR-013), which
  is how its release failed; the earliest target is `v1.0.1`.
- **Staging:** run `deploy.yml` with `workflow_dispatch` and an image tag (`<yyyymmdd>-main-<sha7>`); it deploys that digest
  without building. It applies the Bicep of the branch it runs on (`main`) with the earlier image, so it rolls back the code,
  not the infrastructure. Rehearsed on 2026-11-03: to `v1.0.3`'s image (`20261103-main-f422613`, run 41620351003) in **192 s**,
  and back to `v1.0.4`'s (`20261103-main-88991bd`, run 41620840940) in **188 s**, from dispatch to the new revision serving
  100 %; staging ended on `v1.0.4`.
- **Fastest path:** an earlier revision is kept inactive (up to five).
  `az containerapp revision activate` and `az containerapp ingress traffic set --revision-weight <old>=100 <new>=0` restore it
  without a deployment; the next release brings the Bicep back in line. Not rehearsed in production, so its time, cold start
  included, is not measured; with `v1.0.5` serving, the inactive `v1.0.4` revision (`ca-folium-prod--p5-1-88991bd`) is kept
  as its target (2026-11-10). Planned for the next release.

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

On 2026-11-03 every alert is enabled, its query equals the workbook's, the action group has one confirmed receiver, and none
has fired in 30 days. No alert has been fired on purpose yet (Known limitations).

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
releases) and time to restore (from a failed or rolled-back release to the next successful one). Read on 2026-11-10:

| Metric | Value |
|---|---|
| Deployment frequency, production | 5 successful releases in 7 days: `v1.0.1` and `v1.0.2` on 2026-11-02, `v1.0.3` and `v1.0.4` on 2026-11-03, `v1.0.5` on 2026-11-08 |
| Lead time, merge to production | `v1.0.1` 1 h 23 min, `v1.0.2` 20 min, `v1.0.3` 20 min, `v1.0.4` 1 h 32 min (its one-hour load test included), each with the approval and the ten-minute canary; `v1.0.5`, merged on 2026-11-03, was held for the demo recording and published on 2026-11-08, and its release run took 16 min 32 s |
| Lead time, merge to staging | 3 min 50 s to 4 min 28 s over the last five merges |
| Change failure rate | 1 of 6 release runs (17 %): `v1.0.0` failed in `promote` before production, with no production impact; no release has been rolled back |
| Time to restore | 9 h 46 min, from the `v1.0.0` failure to the `v1.0.1` success |
| Staging deployments | 13 `deploy.yml` runs on merges, 2 failed (2026-10-31), the next success 10 h 28 min later; 2 dispatched runs for the rollback drill, both successful |

## Load tests

`load-test.yml`, manual, from `main`, environment `staging`: the staging digest is redeployed as a revision with
`DOUBLES=load` and made the only active one, then **normal** (5 users, one invoice a minute each, 5 minutes), **peak** (three
20-invoice batches in 2 minutes), **soak** (normal rate, 30 minutes) and **stress** (ramp until p95 passes 30 s or errors pass
1 %); the stable revision is restored and **20 invoices go through the real services**. REQ-10 and REQ-11 are read from
Application Insights from the start of the run to the end of the soak: availability over every request, and the p95 of
`invoice_ready` over the standard invoices that reached it, whose count the gate reports; if both hold, the workflow sets the
`load-test` commit status to `success`. Results, with date, go below. Dispatch it only with no deployment queued: it shares
the `staging` concurrency group with `deploy.yml`, and a newer pending run cancels an older pending one.

p50, p95 and p99 are Locust's `READY invoice` entries: from the upload until the web would show the review card. Requests are
Locust's entries: the uploads, the status reads that poll each invoice every 2 s and one `READY invoice` entry per invoice;
Requests/s and the request counts include all three. Queue, replicas, CPU and memory are maxima over the whole run on the
doubles.

| Run | Scenario | p50 | p95 | p99 | Requests/s | Errors | Users | Queue | Replicas | CPU | Memory |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5, 2026-11-08 | normal, doubles | 16 s | 22 s | 22 s | 0.87 | 0 of 222 requests, 0 of 25 uploads | 5 | 23 | 2 | 0.22 vCPU | 0.46 GB |
| 5, 2026-11-08 | peak, doubles | 25 s | 44 s | 44 s | 3.18 | 0 of 338 requests, 0 of 3 uploads | 60 invoices in 3 batches | 23 | 2 | 0.22 vCPU | 0.46 GB |
| 5, 2026-11-08 | soak 30 min, doubles | 16 s | 18 s | 18 s | 0.75 | 0 of 1,324 requests, 0 of 150 uploads | 5 | 23 | 2 | 0.22 vCPU | 0.46 GB |
| 5, 2026-11-08 | stress, doubles | 16 s | 27 s | 29 s | 9.02 | 0 of 5,589 requests, 0 of 594 uploads | ramp, 10 a minute, stopped at about 103 | 23 | 2 | 0.22 vCPU | 0.46 GB |
| 5, 2026-11-08 | 20 invoices, real services | 43 s | 47 s | 47 s | 2.58 | 0 of 120 requests, 0 of 1 upload | 1 batch | | 2 | | |
| 4, 2026-11-03 | normal, doubles | 16 s | 22 s | 22 s | 0.87 | 0 of 25 uploads | 5 | 20 | 2 | 0.25 vCPU | 0.55 GB |
| 4, 2026-11-03 | peak, doubles | 28 s | 41 s | 41 s | 3.03 | 0 | 60 invoices in 3 batches | 20 | 2 | 0.25 vCPU | 0.55 GB |
| 4, 2026-11-03 | soak 30 min, doubles | 16 s | 16 s | 18 s | 0.73 | 0 of 151 uploads | 5 | 20 | 2 | 0.25 vCPU | 0.55 GB |
| 4, 2026-11-03 | stress, doubles | 16 s | 25 s | 29 s | 8.39 | 0 of 4,945 requests, 0 of 540 uploads | ramp, 10 a minute, stopped at about 98 | 20 | 2 | 0.25 vCPU | 0.55 GB |
| 4, 2026-11-03 | 20 invoices, real services | 46 s | 50 s | 50 s | 2.39 | 0 | 1 batch | | | | |
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

**Run 5 (42498718441, commit `8d7b7d2`, released as `v1.0.5`), 2026-11-08, 16:13 to 17:09 UTC, during the demo recording:
REQ-10 and REQ-11 met.** Over normal, peak and soak, Application Insights gives a p95 of `invoice_ready` of **24.2 s** over 240
standard invoices and an availability of **100 %**; the workflow set `load-test` to `success` on the tested commit. The 240 are
the 235 that Locust counted in normal, peak and soak (25 + 60 + 150) and 5 that normal's users sent as Locust stopped them,
which the app processed but Locust did not record (Application Insights, read on 2026-11-10). No request failed in any
scenario, and every invoice uploaded during the run reached `invoice_ready`, 859 of 859: the 849 that Locust counted
(25 + 60 + 150 + 594 + 20) and 10 that normal's and soak's users sent as Locust stopped them; the soak's 5 were ready after
the soak ended, outside the gate. Replicas, from the app's `Replicas` metric per minute: 1 in normal, 2 from the peak's
batches (16:19), 1 again from 16:27 in the soak, and 2 from 16:59 in stress and in the real-services batch. Peak CPU was 0.22 of 0.5 vCPU and memory 0.46 GB. The real-services batch's upload
was answered after 14 s, because the restored stable revision started from zero. Since `v1.0.4` only documents had changed,
so ADR-014 did not require this run; it ran as part of the recording.

- **Dead-lettered messages: 2, none new** (checked read-only on 2026-11-10). The metrics step reads the maximum of Service
  Bus's `DeadletteredMessages`, which counts the messages sitting in the dead-letter queue, not new arrivals. The two are run
  1's, dead-lettered on 2026-11-01 in the 09:00 UTC hour and never removed: the metric's hourly maximum has been 2 ever since,
  during this run too, and the `invoices` queue of `sb-folium-stg-swc` still held 2 dead-lettered and 0 active messages on
  2026-11-10. Runs 2, 3 and 4 read the same 2. Production's dead-letter queue is empty.

**Run 4 (41609663316, commit `88991bd`, released as `v1.0.4`), 2026-11-03 from 09:16 UTC: REQ-10 and REQ-11 met.** A p95 of
`invoice_ready` of **25.6 s** over the gate's 240 standard invoices, above the 25 s SLO and under the 30 s SLA, and an
availability of **100 %**; no request failed in any scenario. Peak CPU was 0.25 of 0.5 vCPU, memory 0.55 GB, two replicas.
`v1.0.4` changed `infra/`, so this run was its release gate (ADR-014).

**Run 3 (41494700777, commit `f92f034`, released as `v1.0.1`), on `cae-folium-env`, verdict 2026-11-02: REQ-10 and REQ-11
met.** Over normal, peak and soak, Application Insights gives a p95 of `invoice_ready` of **24.2 s** over the gate's 240 standard
invoices and an availability of **100 %**; the workflow set `load-test` to `success` on the tested commit. These are the
figures of the environment that runs today. One status read failed in stress (1 of 5,376 requests, 0.02 %) and no upload failed; the
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
staging from zero replicas (one request each). With `v1.0.4`'s image, on 2026-11-03, staging answered `/healthz` after
**33.0 s** from zero replicas (one request, about two hours idle). Production was not measured with `v1.0.4`: it keeps one
replica in business hours, and the walk-through ran on a warm replica.

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

## Walk-through in production

2026-11-03, 12:07 to 12:11 UTC, on `v1.0.4` (revision `ca-folium-prod--p5-1-88991bd`, which served every request, as
`application_Version` shows), as the accounting lead through the API, with the invoices and reviews of the published demo
(`ops/make_invoices.py --seed 2027`). The nine run files are kept outside the repository; Application Insights in production
holds the events.

| Must | What happened in production |
|---|---|
| REQ-01 | a batch of three (PDF, JPEG, PDF) accepted with `202`, all three ready in 17.8 to 18.9 s |
| REQ-02, REQ-03 | 6 invoices extracted, 15 to 19 fields each; every vendor matched against the seeded master, no `unknown_vendor` |
| REQ-04 | a total mismatch (135.30 expected, 136.30 printed) sent to the lead and rejected with a reason |
| REQ-05 | a probable duplicate of the approved invoice (same vendor and total within 7 days) sent to the lead and rejected |
| REQ-06 | the vendor name read as `Frio` corrected to `Frío`, recorded in the timeline and as one `field_corrected` event |
| REQ-07 | two exports with the same `Idempotency-Key` returned one batch of one invoice; a third found nothing left (`409`) |
| REQ-08 | the exported invoice's timeline: upload, extraction, shield, normalisation (`gpt-5-mini-2025-08-07`, `normalizer_v2`), validation, deduplication, correction, approval and export |
| REQ-09 (Should) | "Show probable duplicates" answered with `[INV-INV-2026-00148]`; an injected invoice got `possible_injection` and skipped the normaliser |
| REQ-10 | business hours on 2026-11-03 to 13:47 Madrid: 4,556 requests, health probes included, 0 server errors (100 %) |
| REQ-11 | p95 ready 19.2 s over 5 standard invoices (8.0 to 19.2 s) |

Events in production on 2026-11-03: 6 `invoice_uploaded`, 6 `invoice_ready`, 1 `field_corrected`, 1 `invoice_approved`,
1 `invoice_exported` and, at 12:38 UTC, the first `feedback` (helpful) through `POST /api/feedback` on the recorded answer to
"Which invoices are waiting for approval?". Since `v1.0.4` was promoted: 2,036 requests, 0 server errors, 0 exceptions, 0 failed
dependencies. Requests are sampled by the Azure Monitor exporter (581 rows stand for 623 requests after 12:00 UTC); KPI events
are not (16 rows, 16 events). The walk-through used the API, as the published demo's runs did; signing in through a browser
and using the deployed web were not part of it; the recording of 2026-11-08 did both (below).

## Recording in production

2026-11-08, on `v1.0.5` (revision `ca-folium-prod--p6-1-8d7b7d2`, at 100 % since release run 42504341261), signed in through
a browser to the deployed production web. Before it, a scripted browser seeded a week of use through the same web (2026-11-06,
and 2026-11-08 from 14:52 to 16:03 UTC, on `v1.0.4`). The load test of the same day is run 5 above.

| Step | What happened in production |
|---|---|
| Release | `v1.0.5` published at 17:18 UTC; `verify` passed, the author approved, and `promote` ran from 17:22 to 17:35 UTC; the ten-minute canary saw only the new revision's health probes (70 requests, 0 server errors) |
| REQ-01 | a text file refused with `415`; a batch of three (PDF, PDF, JPEG) ready in 13.9 to 15.4 s; six more uploads ready in 8.3 to 12.5 s |
| REQ-02, REQ-03 | every field on the card with its confidence and page, and the matched vendor |
| REQ-04, REQ-05 | a total mismatch and a probable duplicate sent to the lead and rejected with a reason |
| REQ-06 | 2 corrections, each in the timeline and as a `field_corrected` event; 4 approvals through the web |
| REQ-07 | five approved invoices exported in one batch; a second export found nothing left |
| REQ-08 | an approved invoice's timeline from upload to approval, with the model and prompt versions |
| Prompt Shields | an invoice with hidden instructions flagged `possible_injection`, with the normaliser skipped, and rejected by the lead |
| REQ-09 (Should) | a cited answer from the assistant; 2 `feedback` events, both helpful |

Events from 17:47 to 18:22 UTC on `v1.0.5`: 9 `invoice_uploaded`, 9 `invoice_ready`, 4 `invoice_approved`, 2 `field_corrected`,
5 `invoice_exported` and 2 `feedback`. The KPI and SLA figures over 2026-11-03 to 2026-11-08 are in the README, all of them
from synthetic use.

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

Open on 2026-11-10, each with its figure and the reason it stays open.

| Limitation | Figure and date | Reason, and when it is revisited |
|---|---|---|
| Production use is synthetic | 85 invoices uploaded, 48 approvals, 43 exports and 24 `feedback` events from 2026-11-03 to 2026-11-08: the walk-through and its rehearsal, the scripted browser's week and the recording | Not client use; production's workbook measures the client's |
| SLA figures not yet over a month | production, 2026-11-03 to 2026-11-08: REQ-10 100 % over 32,261 business-hours request records (to 2026-11-06, health probes included) and REQ-11 20.4 s over 75 standard invoices; the load-test gate gave 100 % and 24.2 s over 240 invoices (run 5, 2026-11-08) | The SLA window is a calendar month of business hours; production's workbook and alerts measure it as use builds up |
| Handling time measured only on synthetic approvals | median 3.4 s over 43 approvals through the web, 2026-11-06 and 2026-11-08, most of them the scripted browser's; the recording's three batch approvals took 318 to 335 s with the cards open during the takes | Only clerks' reviews measure the 2-minute target; re-read with real use |
| The canary watch saw no traffic | `v1.0.2`'s to `v1.0.5`'s ten-minute canaries passed while production served only probes; `v1.0.5`'s saw 70 health probes and 0 server errors, 2026-11-08 | A canary proves something only with traffic; kept as a gate |
| Fast rollback in production not rehearsed | not run for `v1.0.4` or `v1.0.5`, 2026-11-10; the planned rollback in staging took 192 s and 188 s on 2026-11-03 | Residual risk: the time of switching revisions in production, cold start included, is unmeasured. Planned at the next release |
| Alerts not fired on purpose | definitions checked and none fired in 30 days, 2026-11-03; no test notification sent | Residual risk: a delivery fault between the action group and its receiver would go unnoticed. Planned at the next maintenance window |
| REQ-12 erasure (Should) tested only | `test_erase_redacts_personal_fields` passes; neither the refusal inside retention nor an erasure has run live, 2026-11-03 | Invoices are kept six years, so the first erasure of a 2026 invoice is possible in 2033; the live refusal is planned at the next maintenance window, in staging only |
| Assistant's reading of "waiting for approval" | in production it answered "There are no invoices waiting for approval." while two invoices were `ready` (waiting for the clerk's review): it reads the question as `with_lead`, as staging's recorded answer did, 2026-11-03 | REQ-09's citation criterion holds; a wording change in the assistant's prompt goes through the evaluation gate, so it waits for the next prompt change |
| Cost per invoice estimated, not measured | estimate 0.025 €; month to date on 2026-11-02: staging 0.85 € (Cosmos DB), production 0.006 € (Azure Monitor), no Container Apps charge yet | The Foundry and Document Intelligence spend sits in the shared group and cannot be split per product; compared with Cost Management after a month of use |
| Node 26 for the web build stage | Dependabot PR #8 (Node 24.22.2 to 26.12.1) closed by the author on 2026-11-02 | The change is in the `Dockerfile`, a runtime path, so it needs a load test, and the stage only builds static files; Node 24 is supported until 2028-04-30. Revisited at the next release that changes the runtime, or by early 2028 at the latest |
| Storage without zone redundancy | Advisor, High, staging, 2026-11-02 | Single-zone trade-off of the whole product (above) |
| CI principals' privileges | the RBAC Administrator condition of both CI principals still allows *Key Vault Secrets User*, although there is no vault (ADR-009); both hold *Log Analytics Contributor* on the shared workspace, justified in no ADR | Identity changes are the author's; narrowed at the next identity review |
| Required checks | the ruleset requires `python` and `evaluate`; `web` (axe) and `bicep` run on every PR but are not required | GitHub settings are the author's |
| Unused variable | `SHARED_RESOURCE_GROUP` is set in GitHub and listed in the README, but no workflow reads it; the shared group is the Bicep default | Harmless; removed with the next workflow change |
| Steps that rely on the author's scripts | recreating the environment and the sign-in redirect (above) call the author's scripts outside this repository | They hold identity and settings changes, which stay the author's |
| Workflow lint | actionlint 1.7.12 gives four shellcheck notes, none an error: two redirect groupings, one unquoted variable, one unused loop variable | Style only; fixed with the next change to those workflows |
| Code budget at its limit | Python 1,450 of 1,450 and tests 700 of 700 lines | Any code fix must be budget-neutral; the author decides any raise |
| Demo details | in demo mode the composer is disabled with a placeholder, cut on mobile; the profile reads "Demo" until a run plays | The demo replays recorded runs only; free text needs the deployed system |

Closed by the recording of 2026-11-08 ([Recording in production](#recording-in-production)): browser sign-in and the deployed
web, used in production on `v1.0.5`, and handling time, now measured in production (on synthetic approvals, above).
