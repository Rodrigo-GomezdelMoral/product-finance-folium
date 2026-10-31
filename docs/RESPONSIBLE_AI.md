# Responsible AI impact assessment

Following Microsoft's Responsible AI Impact Assessment Template, sections 1 to 5. Assessed on 2026-10-31, at the end of the
evaluation phase; reviewed again before the release.

## 1. System information

| | |
|---|---|
| System | Folium: supplier invoices extracted, validated and de-duplicated, with human review and ERP export |
| Lifecycle stage | Development: workflow, agents and evaluation implemented; API, web and deployment in later phases |
| Description | A clerk uploads invoices. Document Intelligence reads them; Prompt Shields screens their text; one agent, the `Normalizer` on `gpt-5-mini`, completes the tax lines and the withholding; deterministic rules validate them and check duplicates; a person approves. A read-only `Assistant` answers questions about the invoices. |
| Purpose | Give the accounts payable team back the 9 to 19 minutes each invoice takes by hand, and stop duplicates and wrong tax lines before the ERP |
| Features using AI | Field extraction (Document Intelligence `prebuilt-invoice`), prompt injection detection (Prompt Shields), completion of tax lines and IRPF (`Normalizer`), questions in natural language (`Assistant`) |
| Geographic areas and languages | Spain; invoices in Spanish and English from Spanish and EU vendors |
| Deployment | Single tenant, for the employees of one distributor, signed in with Entra ID |

**Intended uses.** (1) Prepare each supplier invoice for review: fields with confidence and source, findings and duplicates.
(2) Answer the team's questions about the invoices, with citations.

## 2. Intended uses

### 2.1 Fitness for purpose

On 60 synthetic invoices with ground truth (`docs/evaluation.md`), header fields are 0.9937 right, line items 0.9186, every
planted error and every duplicate is found with no false finding, and no injected instruction changes anything. The
assistant cites the right invoices in 20 of 20 questions with groundedness 4.2 to 4.65 of 5. The data is synthetic; fitness
on the client's real invoices is measured in staging through the field correction rate and the touchless rate.

### 2.2 Stakeholders, benefits and harms

| Stakeholder | Benefit | Potential harm |
|---|---|---|
| Clerks | Minutes per invoice instead of keying it | Over-reliance: approving fields without looking at the original |
| Accounting lead | Findings and duplicates surfaced before the ERP; a timeline of every decision | Overload if too many invoices are routed to them |
| The distributor | Fewer duplicate payments and wrong VAT returns | An invoice paid twice, or a wrong tax line declared, if a check is missed |
| Vendors | Faster, more consistent processing | Unfair treatment of vendors with unusual formats, whose invoices are read worse and wait longer |
| Sole traders | | Personal data (name, NIF, IBAN) processed and kept for six years |

### 2.3 Goal-driven requirements

- **Human oversight (A5):** the AI never approves, rejects or exports; a clerk or the lead decides every invoice, and only the
  lead resolves findings and duplicates (REQ-04, REQ-05, REQ-06).
- **Intelligibility (T1):** every field shows its confidence and the place on the page it came from; the fields the model
  filled have confidence 0 and are always highlighted; every finding is typed with its evidence.
- **Communication (T2) and disclosure (T3):** the review card, built in phase 5, marks the values read by AI; this document
  and the README state the limitations below.

### 2.4 Fairness

- **Quality of service (F1):** extraction quality differs by layout. Document Intelligence joins line descriptions in one of
  the five layouts and drops accents in vendor names. The cost is extra review time for those vendors, not a different
  decision: the rules and the duplicate checks are the same for all, and the vendor is matched by tax ID first.
- **Allocation (F2):** no resource is allocated by the AI; payment decisions stay in the ERP and with people.
- **Stereotyping (F3):** not applicable; the system makes no statement about people.

### 2.5 to 2.8 Readiness, task, humans, environment

- Every component is generally available: Document Intelligence v4 `2024-11-30`, Prompt Shields `2024-09-01` and `gpt-5-mini`
  `2025-08-07`, pinned with no automatic upgrade. The model retires on 2027-02-09, and a model change passes the evaluation
  gate before it ships. Agent Framework's evaluation API is experimental.
- The task is narrow and checkable: every value has a ground truth on the page.
- People decide; the AI prepares. The deployment is internal, single tenant, at about 1,500 invoices a month.

## 3. Adverse impact

- **Restricted and sensitive uses:** none of Microsoft's restricted uses applies. No consequential decision about a person is
  automated: approval and payment stay with people.
- **Unsupported uses:** approving or paying invoices automatically, e-mail ingestion, handwriting, purchase-order matching,
  other companies' invoices.
- **Known limitations:**
  - Prompt Shields is trained mainly on English. It flagged two of four planted injections, one of them Spanish. The other
    layers held: no field, approval or answer changed.
  - REQ-04 flags recargo de equivalencia, 1 % and 2 % IRPF, discounts and suplidos as findings, and VAT rounded per line can
    exceed 0.01. Invoice numbers that restart every year without the year can look like exact duplicates. Each becomes a
    finding for the lead, never a silent pass.
  - The groundedness judge is the same model as the assistant.
- **Impact of failure:** a missed duplicate is the costliest failure (an invoice paid twice), so duplicate recall must be 1.00
  in the gate. A wrong tax line mis-states the VAT return; the arithmetic and rate rules stop most cases.
- **Impact of misuse:** a vendor who plants instructions in an invoice can at most fill empty tax lines and the withholding
  with amounts printed in the invoice, and the invoice still needs a person's approval.

## 4. Data requirements

- **Classification:** financial documents with personal data of sole traders (name, NIF, address, IBAN).
- **Residency:** stored in `swedencentral`. `gpt-5-mini` is a Global deployment and may process outside the EU, so the IBAN
  never reaches it (ADR-008, phase 6).
- **Retention:** six years for accounting documents; erasure on request after that (REQ-12).
- **Training:** none. No model is trained or fine-tuned; the evaluation data is synthetic and contains no real person.

## 5. Summary of impact

| Harm | Mitigation | Evidence |
|---|---|---|
| Over-reliance on automation | Human approval of every invoice; confidence highlighting; model-filled fields highlighted | `test_clerk_cannot_approve_findings` |
| Paying an invoice twice | Exact and probable duplicate checks block approval and export until the lead resolves them | duplicate recall 1.00 |
| A wrong tax line | REQ-04 rules on rates, bases and totals; the model may only add amounts printed in the document | finding recall 1.00; `test_normalizer_cross_check_rejects_invented_values` |
| Prompt injection in an invoice | Prompt Shields; a tool-less normaliser limited to tax lines and IRPF; the cross-check; a read-only assistant; document text treated as data | injection effect 0 |
| Unfair treatment of unusual formats | Vendor matched by tax ID; the same rules for all; extraction quality measured per run | line item F1, field correction rate in staging |
| Personal data exposure | No IBAN to the model or in the assistant's tools; no key authentication; erasure after retention | `test_assistant_has_no_write_tool`; `no_leak` check |
| Harmful content | Content filters of the shared deployment's guardrail `guardrail-chat`, based on `Microsoft.DefaultV2` | shared base, phase 0 |

**Sign-off:** the author, for this portfolio. A real deployment would need the client's legal, privacy and security review
before release.
