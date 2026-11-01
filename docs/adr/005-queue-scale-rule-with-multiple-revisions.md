# ADR-005 · A queue scale rule with multiple revisions

**Status:** accepted · **Date:** 2026-10-31

## Context

Learn's scaling page (*Scaling in Azure Container Apps*, updated 2026-05-20) says to set `activeRevisionsMode` to single when
using non-HTTP event scale rules. A release must reach production as a canary: a new revision at 0 % behind a label, then 10 %
for ten minutes, then 100 % (OE:11). Traffic splitting needs multiple-revision mode.

## Options

1. **Single-revision mode,** no canary: every release replaces the revision at once.
2. **Two apps:** the API in multiple-revision mode and a worker in single-revision mode. The consumer, which runs the
   workflow, could not be canaried, and the image, identity and settings would be deployed twice.
3. **One app in multiple-revision mode,** with the queue rule on every active revision.

## Decision

Option 3. During a canary both revisions are active, each with its own KEDA rule, and both consume from `invoices`. This is
safe because the consumer claims an invoice from `queued` with its ETag, so each invoice is processed by one revision; a
message for an invoice already past `processing` is completed without work (`test_redelivered_message_is_a_noop`); and the
message contract is versioned: the body is the invoice id, and any change to it ships with a new queue or a version field
that both revisions understand. The previous revision is deactivated on promotion by `deploy.yml` and `release.yml`, and kept
for rollback (`maxInactiveRevisions` 5).

## Consequences

- The canary's 10 % applies to HTTP requests only; queue messages go to whichever replica receives them. The canary watch
  reads server errors of the new revision; a consumer that fails shows as dead-lettered messages, which alert.
- During a canary the two revisions together may run up to six replicas and 60 invoices in flight (ten receivers each,
  ADR-003), at most about 8 analyze submissions per second at 7.5 s per analysis, under 15;
  Document Intelligence 429s are retried by the SDK and then by redelivery.
- `load-test.yml` deactivates the stable revision while the revision with the doubles runs, so no load-test invoice reaches the
  real services through the stable revision's rule.
