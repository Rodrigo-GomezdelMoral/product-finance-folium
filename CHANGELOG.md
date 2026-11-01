# Changelog

All notable changes to Folium are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-01

First release: Folium runs in staging, measured against its SLAs, and is promoted to production by this release.

### Added

- Recorded runs of the deployed system for the published demo (`web/src/demo/runs/`), written by `ops/record.py` from
  staging with real timings and the signed-in user replaced by a role: a batch upload ready for review, a correction and
  approval, findings decided by the lead, a probable duplicate blocked, hidden instructions refused, an export exactly once,
  an invoice's timeline and the assistant's cited answers.
- Load doubles for Document Intelligence and the normaliser's model with their measured latencies (`app/doubles.py`,
  honoured only in staging with `DOUBLES=load`) and `load/locustfile.py` with the normal, peak, soak, stress and real-services
  scenarios; results and verdicts of both load tests in `docs/OPERATIONS.md`.
- The live test in staging, the cold start, the restore drill and the Advisor review in `docs/OPERATIONS.md`.
- In production only, the `business-hours` KEDA cron rule keeps one replica from 08:00 to 19:00 on weekdays (ADR-011).
- Infrastructure as code in `infra/` for staging and production: Container Apps with built-in Entra sign-in, multiple
  revisions, an HTTP and a Service Bus queue scale rule through an identity the code cannot use; Cosmos DB serverless with
  7-day continuous backup; Blob Storage with versioning, soft delete and lifecycle rules; Service Bus Basic with a dead-letter
  queue; Application Insights on the shared workspace, a KPI and SLA workbook, budgets, and SLO alerts in production.
- `deploy.yml` (one image per merge, deployed to staging by digest behind a canary label, health check, smoke test),
  `release.yml` (verification, approval, 10 % canary watched for ten minutes, promotion or rollback) and `load-test.yml`;
  CI builds and lints the Bicep.
- `docs/THREAT_MODEL.md`, `docs/OPERATIONS.md`, `docs/cost.md` and ADR-003 to ADR-011.
- ADR-013: the Container Apps environment and the app in `spaincentral`, the data in `swedencentral`.

- Product specification in `docs/PRODUCT.md`: the client, requirements REQ-01 to REQ-12 with acceptance criteria, the canonical
  invoice, the ERP export layout, KPIs and SLOs.
- The accounts payable process as-is and to-be, as BPMN 2.0 maps with SVG renders.
- Repository foundations: pinned Python dependencies, the container image definition, CI with lint, types, tests and the size
  budget, and Dependabot for pip, GitHub Actions and Docker.
- The canonical invoice and typed findings (`app/models.py`): Spanish tax IDs stored without the `ES` prefix, text fields
  trimmed.
- REQ-04 validation rules and REQ-05 duplicate detection as plain functions (`app/rules.py`), with NIF, CIF and EU VAT checksums
  from `python-stdnum`.
- A synthetic vendor master of 40 vendors, a product catalogue and page templates (`data/`), and `ops/make_invoices.py`, which
  generates 60 invoices from a seed: five layouts in Spanish and English, digital PDFs and degraded scans, 10 planted errors,
  8 duplicates and 4 prompt injections with canaries, with their ground truth.

- The invoice workflow (`app/workflow.py`): a graph per invoice that extracts with Document Intelligence `prebuilt-invoice`,
  screens the text with Prompt Shields, fills what the extraction could not read with a model, validates, checks duplicates
  and pauses for review. Review decisions resume it from a checkpoint, once; a clerk's approval of an invoice with an open
  finding goes to the lead.
- Extraction of every field with its confidence, page and region (`app/extract.py`); the IRPF withholding read as such.
- The `Normalizer` agent on `gpt-5-mini` with a deterministic cross-check: it fills only empty fields and tax bases, every
  value must be printed in the document, and the IBAN never reaches it (`app/agents.py`, `app/prompts/normalizer_v1.md`).
- Vendor matching against the vendor master, by tax ID first and then by name.
- The read-only `Assistant` with its `find_invoices` and `get_invoice` tools (`app/prompts/assistant_v1.md`).
- A timeline on every invoice: each step with its time, the model and prompt versions, every correction and decision.
- Responses of Document Intelligence, Prompt Shields and the model recorded from eight synthetic invoices
  (`tests/fixtures/recorded.json`), replayed by the tests, and a live end-to-end test against the shared services.
- ADR-001 (graph workflow), ADR-002 (one agent) and ADR-012 (code-first, self-hosted agents).
- The evaluation gate (`eval/`): the 60 synthetic invoices and their ground truth, 20 assistant questions with the invoices to
  cite, a 15-invoice smoke suite, metrics for header fields, line items, findings, duplicates, injection effect, groundedness
  (`FoundryEvals`) and citations, thresholds with a baseline, and `.github/workflows/eval.yml`, which runs the smoke suite on
  pull requests that touch the agents, the prompts, the workflow or the evaluation, and the full suite on demand.
- `docs/evaluation.md` with the results and experiment 001 on the normaliser, and `docs/RESPONSIBLE_AI.md`, the responsible AI
  impact assessment.

- The API (`app/main.py`): batch upload with type, size and exact-duplicate checks; invoice list, detail with the timeline, and
  the original streamed through the API; review with corrections; exports in the ERP layout, exactly once per
  `Idempotency-Key`; the streamed assistant with its conversations; feedback; and a health probe. The principal and the
  `Invoice.Process` and `Invoice.Approve` roles come from the platform's sign-in header.
- Storage on Cosmos DB and Blob Storage (`app/store.py`): create-only originals with their hash, ETag on every update, a
  create-only audit trail, duplicate candidates that wait for earlier uploads still in flight, and the export files.
- The queue consumer (`app/worker.py`): claim check through Service Bus, idempotent on the invoice's status and ETag, retries
  by abandoning, and a failed status with the message dead-lettered after the fifth delivery.
- KPI events (`invoice_uploaded`, `invoice_ready`, `field_corrected`, `invoice_approved`, `invoice_exported`, `feedback`) sent
  to Application Insights as custom events and never sampled out (`app/telemetry.py`).
- `ops/erase.py` (REQ-12), `ops/seed.py`, and `ops/compose.yaml` with the Cosmos DB, Azurite and Service Bus emulators.

- The web client (`web/`, React, TypeScript and Vite): the common product interface with a sidebar of invoices waiting for
  review and past conversations, batch upload with a status line per step and the time to ready, a review card with the
  original next to the fields, low-confidence fields marked, findings and duplicates, corrections, and the decisions each role
  may take; the assistant's answers with numbered invoice citations; export with download links; copy and feedback on every
  answer. The browser checks the original's SHA-256 against the stored hash and sends the time the review card was open.
- Demo mode (`VITE_DEMO_MODE=true`): the same client replays recorded runs from `web/src/demo/runs/` without a backend,
  under the band *Demo mode · recorded runs from the deployed system*; the `pages` workflow publishes it to GitHub Pages.
- Keyboard-only flows and axe (WCAG 2.2 AA, no serious or critical violation) on the demo build in CI, with Playwright.
- The container image builds the web client in a Node stage and the app serves it.

### Changed

- The consumer runs ten receivers per replica and the queue scale rule targets ten messages per replica (ADR-003), after
  the first load test.
- Sign-in accepts version 2 access tokens with the client id as audience, so the operator and the CI principal can call
  the API with a bearer token.
- The normaliser fills only the tax lines and the IRPF withholding (`normalizer_v2`); version 1 filled a missing vendor tax ID
  with the customer's. Its cross-check now requires every amount it proposes to be printed in the document.
- The assistant's `find_invoices` lists the finding kinds it accepts and returns each invoice's findings, and `assistant_v2`
  spells out how to cite invoice numbers that already start with `INV-` and invoices without a number.
- The recorded responses in `tests/fixtures/recorded.json` come from `normalizer_v2`.
- New finding kinds: `unknown_vendor`, `rejected_model_value`, `possible_injection` and `model_unavailable`. The withholding
  amount is always stored positive, and the IBAN without spaces.
- Dependabot no longer proposes minor or major Python versions for the base image; the project stays on Python 3.12.
- `GET /api/me` returns the signed-in user's name and roles, and `GET /api/conversations` returns each conversation's turns,
  for the web client. Dependabot watches the web client's npm packages.

### Fixed

- Concurrent uploads raced on the shared Service Bus sender while its link opened and answered `503`; sends are now
  serialised behind a lock.
- The assistant's streamed answer repeated its text, because the final text event of the Responses API replaces what the
  deltas built; the route skips replacing contents.
- `load-test.yml` read only the first value of the gate query's row.
- Checkpoints of invoices read back from Cosmos DB failed to load, because their dates carry pydantic's time zone
  type; the checkpoint allow-list now includes it.
- A review could not resume when the save after an earlier resume had failed; resume now takes the latest checkpoint that
  holds the stored request.

[Unreleased]: https://github.com/Rodrigo-GomezdelMoral/product-finance-folium/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Rodrigo-GomezdelMoral/product-finance-folium/releases/tag/v1.0.0
