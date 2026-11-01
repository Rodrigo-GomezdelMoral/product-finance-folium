# Cost

Estimates from the Retail Prices API (EUR, `swedencentral`, 2026-10-30 and 2026-10-31). The Container Apps environment
runs in `spaincentral` (ADR-013), whose Container Apps meters have the same prices. Phase 7 measures the cost per invoice
in staging, and the end of the build compares these figures with Cost Management per environment.

## Per environment

| | At rest | In use | Budget |
|---|---|---|---|
| Staging | ≈ 0.3 €/month (Cosmos DB and blob storage) | ≈ 7 €/month (evaluation, load tests, real-service runs) | 10 € |
| Production | ≈ 1.5 €/month (three log alerts, one metric alert, storage) | ≈ 3 €/month with demo use | 20 € |
| Client volume (1,500 invoices, 3,000 pages) | | Document Intelligence 26.4 € · `gpt-5-mini` ≈ 5.3 € · Prompt Shields ≈ 1 € · Container Apps ≈ 4 € · the rest ≈ 1.5 € → **≈ 38 €/month, ≈ 0.025 € per invoice**, against 3 to 8 € of manual work | |

## Prices used

| Item | Price |
|---|---|
| Document Intelligence prebuilt | 8.80 € per 1,000 pages |
| `gpt-5-mini` | 0.22 € input, 1.76 € output per million tokens |
| Service Bus Basic | 0.044 € per million operations |
| Cosmos DB serverless | 0.268 € per million RU |
| Container Apps active vCPU | 0.000021 € per second, after the monthly free grant |
| Log alert rule at 15 minutes | 0.44 € each a month |
| Data transfer between `spaincentral` and `swedencentral` | 0.0176 € per GB; about 1 to 3 GB a month at client volume, under 0.10 € (ADR-013) |

The shared base bills whatever Folium does: the registry (≈ 4.40 €/month) and, once Juriscope creates it, AI Search Basic
(≈ 65 €/month). Neither is Folium's cost, and Folium does not use Search.

## What bills while stopped

Cosmos DB and blob storage (cents) in both environments, and the production alert rules. To stop everything without
deleting: disable the alert rules and the Azure workflows (`OPERATIONS.md`).

## Limits that cap the bill

Replicas (2 and 3), four receivers per replica, `max_tokens` 1,500 and 800, 20 files of 10 MB per upload, the shared
deployment's 100K tokens per minute, and the budgets with alerts at 50, 80 and 100 % (CO:04, CO:12).

## Trade-offs not applied

| Option | Monthly cost | Why not now | ADR |
|---|---|---|---|
| Service Bus Standard (duplicate detection, sessions) | 8.61 € | the idempotent consumer replaces duplicate detection | 003 |
| Warm replica in business hours (KEDA cron) | ≈ 3 to 4 € | only if the cold start breaks REQ-11 | 011 |
| Zone redundancy | a VNet environment and replicas always on | ends scale to zero; cold DR within the 4-hour RTO | 011 |
| Data Zone EU model deployment | ≈ +0.5 € at client volume | the IBAN is excluded and the text minimised | 008 |
| Private endpoints | ≈ 596 € (Service Bus Premium alone) plus per-endpoint charges | Basic has none; authentication and local-auth-off cover the surface | 009 |
| Front Door with WAF | 30.80 € Standard, 290.39 € Premium for managed rules | one internal team, platform authentication on every path | 009 |
| Defender plans | per vCore-hour and per image scanned | budget; Dependabot, CodeQL and secret scanning cover the supply chain | 009 |
| WORM immutability | no charge; blocks teardown for six years | write-once in code, versioning and soft delete | 010 |
