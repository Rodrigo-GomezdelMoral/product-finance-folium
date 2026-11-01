# Threat model

A light STRIDE review of Folium as deployed by `infra/` (2026-10-31). Each mitigation names the test or the declaration that
proves it. "Bicep" means the property is declared in `infra/` and checked by `bicep build` and `lint`, and by `what-if` once the author signs in; phase 7
verifies it on the deployed resources.

## Assets and trust boundaries

- **Assets:** the original invoices (financial documents with sole traders' personal data and IBANs), the extracted fields
  and decisions, the audit trail, the export batches that feed the ERP, and the vendor master.
- **Boundaries:** the browser and Container Apps' built-in authentication; the app in `spaincentral` and its data services
  in `swedencentral` (Cosmos DB, Blob Storage, Service Bus), across regions through its managed identity (ADR-013); the
  app and the shared AI services (Document Intelligence, Prompt Shields, `gpt-5-mini`); the invoice's own content, which is
  untrusted input to the model.

## STRIDE

| Threat | Example | Mitigation | Proof |
|---|---|---|---|
| **Spoofing** | A request without a session, or with a forged principal header | Built-in authentication redirects every unauthenticated request to Entra ID except `/healthz`; the principal and roles come only from `X-MS-CLIENT-PRINCIPAL`, which the platform sets and external requests cannot once authentication is configured (ADR-009; see residual risks); without the header the API answers 401, without a role 403 | `test_upload_batch_hash_and_types` (401, 403); Bicep `authConfigs` |
| **Tampering** | An original replaced, an audit entry edited, two writers racing | Originals written once with their SHA-256; audit entries created once; every replace carries the ETag; blob versioning and soft delete | `test_timeline_complete` (hash), `test_export_exactly_once`, `test_redelivered_message_is_a_noop`; Bicep `blobServices` |
| **Repudiation** | "I never approved that invoice" | The timeline records every step, correction and decision with the user's name and time; the audit is append-only | `test_correction_recorded`, `test_timeline_complete` |
| **Information disclosure** | Personal data leaving the tenant or the EU; a key leaked | Data at rest in `swedencentral` and processed in `spaincentral`, both EU (ADR-013); the IBAN never reaches the model and the assistant's tools never return it (ADR-008); local authentication disabled on Cosmos DB, Storage, Service Bus and Application Insights; no public blob access; HTTPS only, TLS 1.2; originals streamed through the API, no SAS | `test_assistant_has_no_write_tool`, eval `no_leak` check (`test_citation_and_leak_checks`); Bicep `disableLocalAuth`, `allowSharedKeyAccess: false`, `DisableLocalAuth`, `allowInsecure: false` |
| **Denial of service** | A flood of uploads or huge files; a runaway bill | 20 files of 10 MB per upload (413), file types by magic bytes (415); at most 2 replicas in staging and 3 in production; ten receivers per replica; one replica in production business hours (ADR-011); `max_tokens` 1,500 and 800; budgets of 10 € and 20 € with alerts at 50, 80 and 100 % | `test_upload_batch_hash_and_types`; `app/agents.py`; Bicep `scale`, `budgets` |
| **Elevation of privilege** | A clerk approves an invoice with findings, exports, or replays someone else's review request | Role checks on review and export; a clerk cannot approve findings or duplicates; the request id given to the workflow is the stored one, read only after the caller is authorised for the invoice; the scale identity is unusable by code (`lifecycle: None`, ADR-006); the app identity holds data roles only, each on its own resource | `test_clerk_cannot_approve_findings`, `test_duplicate_blocks_export`, `test_export_exactly_once` (403 for a clerk), `test_resume_from_checkpoint`; Bicep `identitySettings`, role assignments |
| **Prompt injection in an invoice** | Text in a PDF tells the model to change the total or approve the invoice | Prompt Shields screens the document text and a detected attack skips the normaliser; the normaliser has no tools and every value it returns must appear in the document; the assistant is read-only and treats invoice text as data; no AI step approves or exports | `test_injected_invoice_skips_the_normalizer`, `test_normalizer_cross_check_rejects_invented_values`, `test_assistant_has_no_write_tool`; eval: injection effect 0 on four injected invoices |

## Residual risks

- **First deployment window.** The authentication settings are a child resource applied right after the container app is
  created, so on the first deployment of an environment its first revision is reachable for seconds without the platform's
  sign-in, and a request in that window could forge `X-MS-CLIENT-PRINCIPAL`. The environment is empty at that moment; every later deployment keeps the settings.
- **Global inference.** `gpt-5-mini` may run outside the EU (ADR-008); the IBAN is excluded and the text is minimised.
- **Prompt Shields is trained mainly on English** (Learn, 2026-10-31); Spanish invoices rely on the cross-check, which the
  evaluation covers.
- **No WAF and public endpoints** (ADR-009): the attack surface is the platform's authentication and the API's own limits.
