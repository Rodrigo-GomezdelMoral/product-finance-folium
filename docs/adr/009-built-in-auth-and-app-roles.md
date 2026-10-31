# ADR-009 · Built-in authentication and app roles, with no client secret

**Status:** accepted · **Date:** 2026-10-31

## Context

Users are employees of one tenant. A clerk holds `Invoice.Process`; the accounting lead holds `Invoice.Approve`. The API reads
the principal and roles only from `X-MS-CLIENT-PRINCIPAL`, which only the platform sets. Learn's *Enable authentication and
authorization in Container Apps with Microsoft Entra ID* (updated 2026-02-20) makes the client secret optional: with one,
the hybrid flow returns access and refresh tokens to the token store; without one, the implicit flow returns only an ID
token. The page also warns to avoid the implicit grant where a safer flow is viable.

## Options

1. **MSAL in the web client and token validation in the API:** Python and TypeScript to write, refresh and test.
2. **Built-in authentication with a client secret** kept in Key Vault: a secret to rotate, a vault and a Key Vault reference.
3. **Built-in authentication without a secret.**

## Decision

Option 3 (`infra/modules/app.bicep`, `authConfigs`). Folium never calls another API on the user's behalf, so it needs no
access or refresh token. The ID token is posted to the platform's callback, never handed to the page's JavaScript, and the
platform turns it into its own session cookie; the app roles arrive in it. Unauthenticated requests are redirected to
Entra ID, except `/healthz` for the probes and the canary health check. Bearer tokens for the audience `api://<client id>`
are accepted, so the staging CI principal, given `Invoice.Process` by `04-signin.sh` in phase 7, runs the smoke test and
Locust. The issuer is built from the deployment's tenant, so no identifier is written in the repository.

**No Key Vault.** The build prompt kept a vault only for a sign-in secret "if the platform still needs one"; it does not, so
the vault is not created and the app identity gets no Key Vault role.

**`04-signin.sh` (phase 7) must set** on `folium-<env>`: a web redirect URI `<app URL>/.auth/login/aad/callback`, ID token
issuance, the application ID URI `api://<client id>`, the two app roles with assignment required (`Invoice.Process` allowed for users and applications, so the CI principal
can hold it), and `AUTH_CLIENT_ID` for
the environment.

**Trade-offs not applied** (Retail Prices API, EUR, `swedencentral`, 2026-10-31): private endpoints, which need Service Bus
Premium (0.8162 €/hour, about 596 €/month) and a VNet-integrated environment; Front Door Standard (30.80 €/month base) with
WAF managed rules only on Premium (290.39 €/month base); Defender for Containers (0.0083 € per vCore-hour and 0.2552 € per
image scanned) and for Cosmos DB (0.0011 € per 100 RU/s-hour, priced on provisioned throughput).

## Consequences

- The platform answers `/.auth/login/aad` and `/.auth/logout`; the web client uses the second for sign-out.
- On the very first deployment of an environment, the authentication settings are applied right after the app is created;
  `THREAT_MODEL.md` records that window as a residual risk on an empty environment.
