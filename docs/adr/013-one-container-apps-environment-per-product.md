# ADR-013 · One Container Apps environment per product, in Italy North; data in Sweden Central

**Status:** accepted · **Date:** 2026-11-01, amended 2026-11-02

## Context

The first staging deployment stopped in ARM preflight with `MaxNumberOfRegionalEnvironmentsInSubExceeded`. Managed Environment
Count is a quota per subscription and region (Learn, *Quotas for Azure Container Apps*, 2026-10-09). The `Microsoft.App`
usages API read on 2026-10-31: 1 of 1 in `swedencentral`, taken by another product, and 0 of 5 in `spaincentral`. Phase 0
had read 15. Everything else was built for `swedencentral`: the resource groups, Cosmos DB, Blob Storage, Service Bus, the
identities, Application Insights and the shared base (Foundry, registry, Log Analytics).

The first decision (2026-11-01) moved only the environments and the apps to `spaincentral`, one environment per Folium
environment: `cae-folium-stg-spc` and `cae-folium-prod-spc`. Staging deployed. Release `v1.0.0` then failed creating
`cae-folium-prod-spc` with the same error code. Read again on 2026-11-02, the subscription has two limits:

- **5 environments per subscription.** ARM preflight of a bare environment answers *cannot have more than 5 Container App
  Environments* (`MaxNumberOfGlobalEnvironmentsInSubExceeded`), and 5 exist across the portfolio's products. The usages
  API does not show this limit.
- **1 environment per region.** The usages API reports `ManagedEnvironmentCount` with a limit of 1 in every region read:
  0 of 1 in `italynorth`, 3 of 1 in `spaincentral`.

`az deployment group validate` and `what-if` of `main.bicep` did not catch either limit, because the modules take runtime
values and preflight skips them. Only a module or a bare resource validated with concrete values reaches the provider.

## Options

1. **Quota increases** for both limits. The request may be routed to Azure Support, with no date, and the release waits.
2. **Production in the staging environment.** No quota needed, but production would run in `cae-folium-stg-spc`, owned by
   the staging deployment: a name, an owner and a teardown that all say staging.
3. **A separate region for production only.** Still one environment per Folium environment, so Folium alone takes 2 of the
   subscription's 5, and the next product cannot deploy production.
4. **One environment per product,** `cae-folium-env`, neutral in name, shared by the staging and production apps and owned
   by the production deployment.

## Decision

Option 4, the author's decision. `infra/modules/environment.bicep` declares `cae-folium-env` once, in `italynorth`, with the
`Consumption` workload profile, logs to Azure Monitor and a diagnostic setting to the shared workspace. Only the production
deployment creates it, in `rg-folium-prod-swc` (`environmentGroup`), tagged `environment: shared`. The staging deployment
refers to it as `existing` and never writes it. Both apps run in the environment's region (`environmentLocation`) and keep
their names and resource groups: `ca-folium-stg` in `rg-folium-stg-swc`, `ca-folium-prod` in `rg-folium-prod-swc`. No new
resource group; data stays in `swedencentral`.

Staging deploys first, on every merge, so `06-environment.sh` bootstraps the environment before the next deployment: it deletes
`ca-folium-stg` and `cae-folium-stg-spc` (the subscription limit allows no sixth environment), deploys
`environment.bicep` with the same parameters as production, so the next release finds no drift, and grants the staging
CI principal a custom role on the environment alone with `Microsoft.App/managedEnvironments/read` and
`Microsoft.App/managedEnvironments/join/action` ("Allows to create a Container App in a Managed Environment", Learn, *Azure
permissions for Compute*, 2026-07-01).

The environment lives with production because production's lifecycle governs it: removing or pausing staging never touches
it, the staging principal can join it but not change it, and its settings change only through a reviewed release.

Elevant, Juriscope and Trainyard follow the same pattern: one `cae-<product>-env` each, owned by production, in a region where
the product has the regional slot. Four products then use 4 of the subscription's 5 environments.

Checked on 2026-11-02:

- The `Microsoft.App` provider lists Italy North for `managedEnvironments` and `containerApps` at API version `2026-07-01`,
  and the region offers the `Consumption` workload profile type (`availableManagedEnvironmentsWorkloadProfileTypes`).
- Built-in authentication and Service Bus scale rules with a managed identity have no region condition (Learn, 2025-12-04
  and 2026-05-19, as checked on 2026-10-31). The KEDA scaler reaches the namespace by name over its public endpoint.
- Preflight of `environment.bicep` in `rg-folium-prod-swc` and `italynorth` reaches the provider and fails only on the
  subscription limit while 5 environments exist; preflight of `app.bicep` with concrete values succeeds.

## Consequences

- **Shared environment-level settings.** Staging and production share the log destination, the networking (one default
  domain and one internal network), the platform's upgrades and the environment's availability. The apps, identities,
  data, secrets, sign-in registrations, scale rules and revisions stay per environment. A change to the environment ships
  only through `release.yml`, so staging does not rehearse it first; `what-if` in the release shows it.
- **Removal.** Deleting `rg-folium-prod-swc`'s resources deletes the environment and stops staging too. Removing staging
  deletes only `ca-folium-stg` and its data.
- **Latency.** The P50 round trip between Italy North and Sweden Central is 38 ms (Learn, *Azure network round-trip latency
  statistics*, 2026-07-30), against 50 ms from Spain Central. An invoice makes about 20 to 30 calls to the data and AI
  services, so about 0.8 to 1.1 s more against REQ-11's 30 s. The load test in staging measures it again in the new region.
- **Egress.** Traffic between regions bills at 0.018 €/GB (Retail Prices API, *Standard Inter-Region Data Transfer*, the same
  in `swedencentral` and `italynorth`, 2026-11-02): about 1 to 3 GB a month at client volume, under 0.10 €.
- **Residency.** Data at rest stays in `swedencentral`. The apps process it in `italynorth` (Milan) and store nothing there.
  Both regions are in the EU, so ADR-008's statement holds. Traffic between them uses TLS 1.2 or later on public endpoints
  with Entra ID. The environment's logs go to the shared workspace in `swedencentral`.
- **Availability.** The service depends on two regions, and an outage in either one stops it. Cold recovery stays as in
  ADR-011: run `06-environment.sh` with another region and `environmentLocation`, then redeploy both environments.
- **Host names change.** Both apps get new ingress host names in the new environment, so `04-signin.sh` runs after the first
  staging deployment and again after the first production deployment to update the redirect URIs.
