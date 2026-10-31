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

### Changed

- Dependabot no longer proposes minor or major Python versions for the base image; the project stays on Python 3.12.

[Unreleased]: https://github.com/Rodrigo-GomezdelMoral/product-finance-folium/commits/main
