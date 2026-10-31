# ADR-002 · One agent, only where a function cannot do the job

**Status:** accepted, scope narrowed by experiment 001 · **Date:** 2026-10-31

## Context

Document Intelligence `prebuilt-invoice` (API `2024-11-30`) returns typed fields with a confidence and a bounding region.
Its schema has no withholding field, and `TaxDetails` holds only `Amount` and `Rate` (a string), without the taxable base.
On the recorded invoices, it returned the IRPF withholding of Spanish professionals and sole traders as one more `TaxDetails`
line with a negative amount. The taxable base printed next to each VAT rate, and any field it misses, cannot be read by a rule.
Everything else in the process (mapping, the withholding, matching the vendor master, the REQ-04 rules, duplicates, routing
the review) is deterministic.

## Options

1. **No model.** Invoices with withholding always fail the total check and go to the lead.
2. **A model reads the whole invoice** and its output replaces the extraction. Every value becomes as reliable as the model,
   and a prompt injected in the invoice reaches every field.
3. **One agent, `Normalizer`, that only fills what the deterministic mapping left empty,** behind a deterministic
   cross-check.

## Decision

Option 3, in `app/agents.py`:

- `Normalizer` is an `Agent` on `gpt-5-mini` with `response_format=CanonicalInvoice`, `max_tokens` 1,500, `store` off,
  reasoning effort `minimal` and a 15-second timeout per attempt. It has no tools. Its instructions are
  `app/prompts/normalizer_v2.md` (`normalizer_v1.md` is kept as the measured predecessor), and the version is written to the
  invoice's timeline with the model version that answered.
- **The mapping, not the model, reads the withholding:** `app/extract.py` turns a `TaxDetails` line with a negative amount into
  `irpf`. In the first recording the model, asked to fix the tax lines, kept the withholding among the VAT lines of one invoice.
- The model fills **only the tax lines and the IRPF withholding** (`FILLABLE`): the taxable base of each tax line the mapping
  read, matched by rate and amount; the tax lines when the mapping read none; the withholding when the mapping did not read it.
  Whatever else it returns is ignored, and it never replaces a value the mapping read. Version 1 filled any empty field; the
  evaluation showed it filling a missing vendor tax ID with the customer's, printed on the same page.
- **Cross-check:** every amount it proposes must be printed in the document text that Document Intelligence read, under either
  decimal convention. An amount that is not printed is rejected and becomes a `rejected_model_value` finding, so the invoice goes
  to the lead.
- **The IBAN never reaches the model:** every line labelled IBAN and every IBAN-shaped string is replaced before the call,
  and `iban` is excluded from the mapped fields it receives and from what it may return.
- Fields it filled get confidence 0, so the review card always highlights them.
- If the model fails (a `ChatClientException`: 429 after the SDK's retries, timeout, content filter), the invoice keeps the
  Document Intelligence mapping and gets a `model_unavailable` finding.
- The withholding amount is stored positive by the canonical model itself: Document Intelligence returns it negative, and so
  did the model in the first live call.

Measured on 2026-10-31 against the shared base:

- `gpt-5-mini` (version `2025-08-07`) on one synthetic invoice: 4.7 s with effort `minimal` and no reasoning tokens, 6.0 s with
  `low` and 320 reasoning tokens, the same output.
- Eight recorded invoices (`tests/fixtures/recorded.json`: Spanish and English layouts, two scans, an EU vendor, three with
  withholding, two with injected instructions): the mapping alone equals the ground truth on every field except the taxable
  bases and the 0 % VAT line of the EU invoice; with the normaliser, all six invoices it saw equal the ground truth on every
  field. Prompt Shields flagged both injected invoices, the Spanish one included, so the model never saw them.

## Consequences

- The model cannot introduce a value that is not in the document, and cannot change a value the extraction read.
- A prompt injected in an invoice can at most fill empty tax lines and the withholding with amounts printed in it, and a
  detected attack skips the model.
- Measured in experiment 001 (`docs/evaluation.md`, 60 invoices, 2026-10-31): without the normaliser, header accuracy is 0.9018
  and finding precision and recall 0.59 and 0.83; with `normalizer_v2`, 0.9937 and 1.00 and 1.00. The agent stays.
