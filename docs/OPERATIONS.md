# Operations

How Folium is promoted, watched, restored and paid for. Status on 2026-10-31: the infrastructure, the three workflows and
this runbook are written, and the Bicep passes `bicep build` and `lint`; `what-if` for both environments waits for the
author's sign-in; the first deployment to staging, the load
tests, the restore drill and the Advisor review are phase 7 work, and their results are added here with their dates.

## Environments and promotion

| | Staging | Production |
|---|---|---|
| Resource group | `rg-folium-stg-swc` | `rg-folium-prod-swc` |
| App | `ca-folium-stg`, 0 to 2 replicas | `ca-folium-prod`, 0 to 3 replicas |
| Data | `cosmos-folium-stg-swc`, `stfoliumstgswc`, `sb-folium-stg-swc` | `cosmos-folium-prod-swc`, `stfoliumprodswc`, `sb-folium-prod-swc` |
| Telemetry | `appi-folium-stg-swc`, workbook | `appi-folium-prod-swc`, workbook, `ag-folium-prod-swc` and four alerts |
| Changed by | `deploy.yml`, on every merge to `main` | `release.yml`, on a published release, after the author's approval |

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
- **Drill:** rehearsed in staging in phase 7; the measured RTO goes here.

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

- **At rest** both apps scale to zero by themselves (minimum 0 replicas); check with
  `az containerapp replica list -n ca-folium-<env> -g <rg> --revision <revision>`. Staging ends every phase at zero.
- **Pause production without deleting:** disable the three log alerts (`az monitor scheduled-query update --disabled true`)
  and the deploying workflows (`gh workflow disable deploy.yml`, `release.yml`, `load-test.yml`). What still bills: Cosmos DB
  and blob storage (cents).
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
Results, with date, go below in phase 7. Dispatch it only with no deployment queued: it shares the `staging` concurrency
group with `deploy.yml`, and a newer pending run cancels an older pending one.

| Date | Scenario | p50 | p95 | p99 | Requests/s | Errors | Users | Queue | Replicas | CPU | Memory |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Azure Advisor

`az advisor recommendation list` at the close of every deploying phase; each recommendation is applied when free or
justified here. First review: phase 7.
