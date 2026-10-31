# ADR-007 · Shared registry, Foundry account and Log Analytics workspace

**Status:** accepted · **Date:** 2026-10-31

## Context

The shared base in `rg-aiplatform-shared-swc` serves several products: the registry `craiplatformshared` (Basic, about
4.40 €/month whoever uses it), the Foundry account `fdry-aiplatform-shared-swc` with the `gpt-5-mini` deployment, Document
Intelligence and Content Safety, and the workspace `log-aiplatform-shared-swc`.

## Options

1. **Folium's own registry, AI account and workspace per environment:** three more resources per environment, a registry
   billed every day in each, and a model deployment and quota to own.
2. **Use the shared base, read-only,** and add only role assignments for Folium's identities.

## Decision

Option 2. Folium's Bicep never changes a shared resource. Its module `infra/modules/shared.bicep` grants the app identity
AcrPull on the registry, Cognitive Services User on the account (Document Intelligence and Prompt Shields) and Foundry User on
the project, through the CI principals' RBAC Administrator condition limited to exactly those roles. The module is a nested deployment in
the shared resource group, which RBAC Administrator does not allow, so each CI principal also holds the custom role *Folium
shared-base deployments* there (`Microsoft.Resources/deployments/*` only), given by the author's `03-shared-deployments.sh`. Images are built once,
pushed by the staging principal and promoted to production by digest (OE:06). Each environment has its own Application
Insights, workspace-based on the shared workspace, so the environment is the telemetry dimension; the Container Apps
environment sends its logs there through a diagnostic setting (destination `azure-monitor`), with no workspace key.

## Consequences

- Retention is the shared workspace's minimum (CO:10); Folium adds no workspace.
- The shared deployment's 100K tokens per minute serve every product: the eval gate and the load tests run against staging
  with doubles or small suites.
- The registry and, once it exists, AI Search bill whatever Folium does; `docs/cost.md` keeps them out of Folium's cost.
