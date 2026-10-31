# Changelog

All notable changes to Folium are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- The normaliser fills only the tax lines and the IRPF withholding (`normalizer_v2`); version 1 filled a missing vendor tax ID
  with the customer's. Its cross-check now requires every amount it proposes to be printed in the document.
- The assistant's `find_invoices` lists the finding kinds it accepts and returns each invoice's findings, and `assistant_v2`
  spells out how to cite invoice numbers that already start with `INV-` and invoices without a number.
- The recorded responses in `tests/fixtures/recorded.json` come from `normalizer_v2`.
- New finding kinds: `unknown_vendor`, `rejected_model_value`, `possible_injection` and `model_unavailable`. The withholding
  amount is always stored positive, and the IBAN without spaces.
- Dependabot no longer proposes minor or major Python versions for the base image; the project stays on Python 3.12.

[Unreleased]: https://github.com/Rodrigo-GomezdelMoral/product-finance-folium/commits/main
