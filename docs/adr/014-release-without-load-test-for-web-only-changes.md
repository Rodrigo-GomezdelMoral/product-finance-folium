# ADR-014 · A release without a new load test when only the web, docs or workflows changed

**Status:** accepted · **Date:** 2026-11-02

## Context

`release.yml` promotes a tag only when its commit was deployed to staging on merge (`deploy.yml`) and carries a `load-test`
commit status of `success`. A load test runs normal, peak, a 30-minute soak and stress in staging, and it
measures the API: the time from upload to ready (REQ-11) and its availability (REQ-10). A change to the web client, the
documents or the workflows does not change what the API runs: the client is static files served by the same app, and the
documents and workflows never reach the container at runtime. Requiring a new load test for such a release costs the run and
measures nothing that changed.

## Options

1. **Always require the load test** on the tagged commit. Simple, and every web or documentation fix waits for a full load
   test in staging and pays for it.
2. **A manual override** (a `workflow_dispatch` input that skips the check). Fast, and it depends on the operator's judgement
   at release time, with no record of why.
3. **Decide from the changed paths.** Compare the tag with the last release that reached production and skip the load test only when
   every changed path is outside the API's runtime.

## Decision

Option 3, the author's decision of 2026-11-02. Job `verify` of `release.yml` checks out the history with every tag, always
requires a successful `deploy.yml` run on the tagged commit, and finds the last earlier release that reached production:
published, not a pre-release, ordered by publication date, and with a successful `release.yml` run on its release event. A
failed release never reached production, so it is never the baseline. The job lists the paths changed between that
release's tag and this tag's commit and prints each one as `exempt` or `runtime`. The load test is not required when every path matches `web/**`, `docs/**`,
`.github/**` or any `*.md`. Any other path, or no earlier release in production, requires `load-test` `success` as before. The
job log states the decision.

## Consequences

- A web-only release (for example the client's layout) goes from merge to production without a load test; its staging
  deployment and smoke test still run on merge, and production keeps the canary at 10 % with its server-error watch.
- The comparison is against the last release in production, which itself passed the gate, so a chain of web-only releases
  never hides an API change: the first release that touches anything else requires the load test again.
- `.github/**` is exempt because workflows change how the service is built and deployed, not what it runs; a workflow change
  that alters the image (for example its build arguments) must also change a runtime path, such as the `Dockerfile`, to be
  load-tested.
- A rollback with `workflow_dispatch` is compared with the last release in production published before the tag it
  promotes. Promotions by `workflow_dispatch` do not count as a baseline, because the run does not record its tag in the
  run list; only release events do.
