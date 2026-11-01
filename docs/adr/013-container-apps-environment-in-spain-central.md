# ADR-013 · Container Apps environment in Spain Central, data in Sweden Central

**Status:** accepted · **Date:** 2026-11-01

## Context

The first staging deployment stopped in ARM preflight with `MaxNumberOfRegionalEnvironmentsInSubExceeded`. Managed Environment
Count is a quota per subscription and region (Learn, *Quotas for Azure Container Apps*, 2026-10-09). The `Microsoft.App`
usages API read on 2026-10-31: 1 of 1 in `swedencentral`, taken by another product, and 0 of 5 in `spaincentral`. Phase 0
had read 15. Folium needs two environments, staging and production. Everything else was built for `swedencentral`: the
resource groups, Cosmos DB, Blob Storage, Service Bus, the identities, Application Insights and the shared base (Foundry,
registry, Log Analytics).

## Options

1. **A quota increase in `swedencentral`.** The request may be routed to Azure Support, with no date, and phase 7 waits.
2. **Share the other product's environment.** Couples two products' deployments, scale and teardown (SE:04 segmentation).
3. **Move all of Folium to `spaincentral`.** New names and new data accounts, still calling the shared base in
   `swedencentral`.
4. **Only the environment and the app in `spaincentral`;** data and everything else stay where they are.

## Decision

Option 4, the author's decision. `infra/main.bicep` takes `appLocation` (default `spaincentral`, allowed `swedencentral` and
`spaincentral`) for the environment and the app only; `app.bicep` adds the region's code to the environment's name:
`cae-folium-stg-spc` and `cae-folium-prod-spc`. The app keeps `ca-folium-<env>` and both stay in `rg-folium-<env>-swc`.
Nothing else is renamed or recreated.

Checked on 2026-10-31:

- The `Microsoft.App` provider lists Spain Central for `managedEnvironments` and `containerApps` at API version `2026-07-01`,
  and the region offers the `Consumption` workload profile type (`availableManagedEnvironmentsWorkloadProfileTypes`).
- Built-in authentication runs as a sidecar of any app with external ingress, with no region or profile condition (Learn,
  *Authentication and authorization in Azure Container Apps*, 2025-12-04).
- Scale rules for Service Bus accept a managed identity, with no region condition (Learn, *Scaling in Azure Container Apps*,
  2026-05-19). The KEDA scaler reaches the namespace by name over its public endpoint, as before.
- Spain Central (Madrid) is in Europe, with three availability zones and no paired region (Learn, *List of Azure regions*).

## Consequences

- **Latency.** The P50 round trip between the two regions is 50 ms (Learn, *Azure network round-trip latency statistics*,
  2026-07-30). Every call from the app to Cosmos DB, Blob Storage, Service Bus, Foundry and Application Insights pays it. An
  invoice makes about 20 to 30 of those calls, so about 1 to 1.5 s more against REQ-11's 30 s. Document Intelligence (7.4 to
  9.6 s) and the model still dominate. Phase 7's load tests measure the real figure in staging.
- **Egress.** Traffic between regions bills at 0.0176 €/GB (Retail Prices API, *Standard Inter-Region Data Transfer*, the same
  in both regions, 2026-10-31). An original crosses up to three times (to Blob Storage, back for analysis, to Document
  Intelligence), plus documents, messages, telemetry and logs. That is about 1 to 3 GB a month at client volume, under
  0.10 €. Container Apps meters in `spaincentral` have the same prices as in `swedencentral`.
- **Residency.** Data at rest stays in `swedencentral`. The app processes it in `spaincentral` and stores nothing there.
  Both regions are in the EU, so ADR-008's statement holds. Traffic between them uses TLS 1.2 or later on public endpoints
  with Entra ID. The environment's logs go to the shared workspace in `swedencentral`, because diagnostic settings accept a
  workspace in another region.
- **Availability.** The service now depends on two regions, and an outage in either one stops it. Cold recovery stays as in
  ADR-011: redeploy with another `appLocation`. A new region also needs its code in `app.bicep`.
- **Reversible.** A resource cannot change region. Once `swedencentral` has quota, delete the app and its environment, then
  deploy with `appLocation: 'swedencentral'` to create `cae-folium-<env>-swc` and a new app. The ingress host name changes,
  so `04-signin.sh` must run again to update the redirect URI.
