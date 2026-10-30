# <img src="docs/images/brand/folium-icon.svg" alt="" height="40"> Folium

Built by **Rodrigo Martín Gómez del Moral Herranz**

<a href="https://github.com/Rodrigo-GomezdelMoral"><img src="docs/images/author/github.png" alt="GitHub" height="36"></a>&nbsp;&nbsp;<a href="https://www.linkedin.com/in/rodrigo-mart%C3%ADn-g%C3%B3mez-del-moral-herranz"><img src="docs/images/author/linkedin.png" alt="LinkedIn" height="36"></a>&nbsp;&nbsp;<a href="https://rodrigogomezdelmoralherranz.es"><img src="docs/images/author/portfolio.png" alt="Portfolio" height="36"></a>

Invoice data extracted, validated and de-duplicated, with human review and ERP export. Folium is for an accounts payable team
that keys 1,500 supplier invoices a month by hand, 9 to 19 minutes each, and finds duplicates and wrong tax lines only at
reconciliation, weeks later.

**Status:** the product is specified and the repository is set up. The code arrives phase by phase; the published demo comes
with the release.

## The problem

A mid-size Spanish wholesale distributor receives about 1,500 invoices a month from about 400 vendors, as PDFs and scans, with a
month-end peak of about 150 a day. Three clerks key every one of them into the ERP: read it, look up the vendor, key the header and
the lines, check the totals and VAT by hand, search for a duplicate and file the PDF. That is 225 to 475 hours a month, and the
mistakes it lets through, an invoice entered twice or a wrong tax line, surface only at reconciliation.

![Accounts payable today: eight manual steps by the clerk, 9 to 19 minutes per invoice](docs/images/process-as-is.svg)

## What it does

As specified in [`docs/PRODUCT.md`](docs/PRODUCT.md):

- Reads each invoice with Document Intelligence and returns every field with its confidence and the place on the page it came from.
- Normalises it to one schema and matches the vendor, calling a model only where a rule cannot decide, and rejects any value the
  model did not read in the document.
- Validates Spanish VAT and IRPF rates, tax IDs, dates and arithmetic, and blocks exact and probable duplicates.
- Puts the original next to the fields for the clerk; invoices with findings go to the lead, and the AI never approves or exports.
- Exports approved invoices in the ERP layout exactly once, with a timeline of every step and decision.

![Accounts payable with Folium: the clerk uploads and reviews, Folium prepares each invoice, the lead resolves findings and exports](docs/images/process-to-be.svg)

## Requirements

| ID | Priority | Requirement | Status |
|---|---|---|---|
| REQ-01 | Must | Upload one invoice or a batch of up to 20 | Specified |
| REQ-02 | Must | Extract every field with its confidence and source | Specified |
| REQ-03 | Must | Normalise to the canonical schema and match the vendor | Specified |
| REQ-04 | Must | Validate mandatory fields, arithmetic, tax rates, tax IDs and dates | Specified |
| REQ-05 | Must | Detect exact and probable duplicates | Specified |
| REQ-06 | Must | Review and correct, with every correction recorded | Specified |
| REQ-07 | Must | Export approved invoices exactly once in the ERP layout | Specified |
| REQ-08 | Must | Full traceability per invoice | Specified |
| REQ-10 | Must · SLA | 99.5 % availability in business hours | Specified |
| REQ-11 | Must · SLA | 95 % of standard invoices ready for review in under 30 s | Specified |

The two Should requirements, a read-only assistant (REQ-09) and erasure on request (REQ-12), and every acceptance criterion are in
[`docs/PRODUCT.md`](docs/PRODUCT.md).

## KPIs

| KPI | Target |
|---|---|
| Handling time per invoice | 2 min or less, from 9 to 19 today |
| Touchless rate | 70 % or more approved with no correction |
| Field correction rate | 5 % or less of extracted fields |
| Feedback | 80 % or more positive |

They are measured from events in Application Insights once Folium runs in staging.

## Documentation

- [`docs/PRODUCT.md`](docs/PRODUCT.md): client, process as-is and to-be, requirements with acceptance criteria, KPIs, SLOs and
  the ERP export layout.
- [`CHANGELOG.md`](CHANGELOG.md).

## Author

**Rodrigo Martín Gómez del Moral Herranz**

<a href="https://github.com/Rodrigo-GomezdelMoral"><img src="docs/images/author/github.png" alt="GitHub" height="36"></a>&nbsp;&nbsp;<a href="https://www.linkedin.com/in/rodrigo-mart%C3%ADn-g%C3%B3mez-del-moral-herranz"><img src="docs/images/author/linkedin.png" alt="LinkedIn" height="36"></a>&nbsp;&nbsp;<a href="https://rodrigogomezdelmoralherranz.es"><img src="docs/images/author/portfolio.png" alt="Portfolio" height="36"></a>
