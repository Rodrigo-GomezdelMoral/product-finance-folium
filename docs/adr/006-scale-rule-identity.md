# ADR-006 · A separate identity for the queue scale rule

**Status:** accepted · **Date:** 2026-10-31

## Context

KEDA's `azure-servicebus` scaler reads the queue's message count from its runtime properties, which needs the *Manage* claim;
in Azure RBAC that is *Azure Service Bus Data Owner*. Learn's *Managed identities in Azure Container Apps* (updated
2026-02-13) shows `identity` on scale rules and `identitySettings` with `lifecycle: None` for "a managed identity that is only
used for ACR image pull, scale rules, or Key Vault secrets"; it appeared in API `2024-02-02-preview`. Neither that page nor
*Scaling in Azure Container Apps* (2026-05-20) names the minimum Service Bus role, and third-party guides disagree between
Data Receiver and Data Owner (search of 2026-10-31).

## Options

1. **The app identity with Data Owner.** The code could then create, change or delete the queue.
2. **A connection string with a Manage policy.** A secret, and local authentication is disabled on the namespace (SE:09).
3. **A second user-assigned identity,** `id-folium-<env>-scale`, Data Owner on the queue `invoices` only, attached to the app
   with `lifecycle: None`, so no container can obtain its tokens.

## Decision

Option 3, with `Microsoft.App` API `2026-07-01`, the latest GA version in Bicep 0.48.1's type index, which accepts
`identitySettings` with no warning. Data Owner stays until a live test shows less is enough: phase 7 checks that the rule
scales with messages waiting, then gives the identity Data Receiver instead on a staging revision; if replicas still follow
the queue, Data Receiver replaces Data Owner and this ADR records the result.

## Consequences

- The app identity keeps Data Sender and Data Receiver; nothing the code runs as can manage the namespace (SE:05).
- The CI principals' RBAC Administrator condition already lists Data Owner among the environment roles.
