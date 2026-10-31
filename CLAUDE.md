# CLAUDE.md, working agreement

`product-finance-folium` is **Folium**: supplier invoices extracted, validated and de-duplicated, with human review and ERP export,
for the accounts payable team of a mid-size Spanish wholesale distributor. A staff engineer and a product manager will read this
repository for ten minutes and must conclude that the author ships products a company would put in front of its customers: a
client with requirements, metrics that prove the value, and a safe way to change it.

Three rules govern every choice:

> **If a capability exists in an Azure service or in Microsoft Agent Framework, do not reimplement it.**
>
> **Every framework feature used here must replace code that would otherwise exist.**
>
> **If a function can do the task, write the function, not an agent.**

**Re-read this file at the start of every phase** and reason the plan before touching code: which `REQ` the phase closes (see
`docs/PRODUCT.md`) and how it will be proven.

## Process

- The build prompt is `../_prompts/V5-CC-P06-product-finance-folium.md`, run phase by phase with
  `../_00_MASTER_PROMPTS_PRODUCT/02_EJECUTAR_PROMPT_POR_FASES.md`. Both are read in full; this file does not replace them.
- **Trunk-based.** One short branch per phase, created with `git switch -c` from `main` updated with `git pull --ff-only`:
  `feature/setup`, `domain`, `agents`, `eval`, `api`, `web`, `infra`, `staging`, `release`. No environment branches.
- **Commits, pushes, PRs, merges and releases are the author's.** Never run `git add`, `git commit`, `git push`, `gh pr create`, a
  merge, a force push or an amend, and never delete branches. No `Co-Authored-By` of Claude and no Claude Code line anywhere.
- **Closing a phase, in this order:** ruff, mypy, pytest and `tests/test_budget.py`, plus the phase's own checks; conformity with
  its `Guidance map` rows; the block below; the publish script `../_scripts/product-finance-folium/publish-<branch>.sh` (template
  7.3 of `../_00_MASTER_PROMPTS_PRODUCT/_setup/CONFIGURACION_INICIAL.md`: only the phase's paths, the commit in English, the PR to
  `main` with the phase summary); `git status --short` and the script path; stop until the author merges and says "continue".

  ```
  ── PHASE n COMPLETE ──
  Files: <n>/90   Python: <n>/1400   Tests: <n>/700   Bicep: <n>/490   TS: <n>/800   Comments: <n>/5
  Verified: ruff ✓  mypy ✓  pytest ✓  budget ✓  <phase checks>
  Requirements: REQ-xx <test> <live evidence or "local only"> · ...
  Guidance: <syllabus sections> · <Well-Architected codes>
  Publish with: ../_scripts/product-finance-folium/publish-<branch>.sh
  ```

  The counts come from `python -c "from tests.test_budget import budget_counts; print(budget_counts())"`.
- **Identity is the author's.** Roles, federated credentials, app registrations and app-role assignments go in
  `../_scripts/product-finance-folium/<nn>-<what>.sh`; write the script and stop. Phase 7 writes `02-signin.sh`.
- **Azure only in phases 7 and 8.** Before that: emulators, doubles, `bicep build`, `lint` and `what-if`. The exception is phases
  2 and 3, which call the shared base's `gpt-5-mini`, Document Intelligence and Content Safety, billed per use. Before creating
  anything that bills by the hour, state its price and how it is switched off. Staging ends every phase at zero replicas.
- **Verify, then write.** Every Agent Framework and Azure SDK name against the installed wheel; every Bicep API version, CLI flag
  and GA or preview status against Microsoft Learn, with the date. Say whether a thing is implemented, tested, deployed to
  staging, deployed to production or pending.
- **English** in everything generated. The author is spoken to in Spanish.

## Non-negotiable constraints

1. **No identifiers anywhere:** no GUID, e-mail address, Azure resource hostname, public IP or local user path in files, fixtures,
   recorded runs, commits or docs. Resource names are fine. `tests/test_budget.py` scans every file and reports only the file and
   the kind of identifier, never the value.
2. **Zero secrets.** Managed identities and `DefaultAzureCredential`; local authentication disabled on every service that allows it.
3. **Budgets, enforced by `tests/test_budget.py`** (non-empty lines): Python in `app/ eval/ load/ ops/` at most 1,400; tests at
   most 700; Bicep at most 490; TypeScript under 800; files at most 90, excluding `docs/`, `data/`, `eval/datasets/`,
   `web/node_modules/`, `web/src/demo/runs/` and lock files.
4. **Comments:** at most 5 `#` comments in the whole codebase: Python, YAML, TOML, requirements, shell, `Dockerfile` and
   `Makefile`. The only exempt `#` is the version tag after a SHA-pinned action, which Dependabot maintains. The why lives in
   the ADRs and the README.
5. **No bare `except Exception`.** Catch the SDK's own exceptions.
6. **Pinned dependencies:** `==` in both requirements files, GitHub Actions pinned by commit SHA, base images by digest. Never the
   `agent-framework` metapackage.
7. **Nothing unfinished:** no to-do markers (ruff `FIX`), no placeholder text, no dead code.
8. **Authorship only in the README:** the byline and buttons under the title and `## Author` at the end. `LICENSE` stays the
   unfilled Apache-2.0 template; no author in `pyproject.toml`; never an e-mail.
9. **README** with the common structure of `../_00_MASTER_PROMPTS_PRODUCT/07_README_FINAL.md`: no quick start, no local run
   instructions, no status badges, no em dashes. The product is tried through the published demo.

## Local development

Python 3.12. CI runs `make install` and `make check` on Ubuntu. On Windows without `make`, from a virtual environment:

```
python -m pip install -r requirements-dev.txt
python -m ruff check . && python -m ruff format --check . && python -m mypy && python -m pytest -q
```

`tests/test_live.py` runs the workflow end to end against the shared base only when `FOUNDRY_ACCOUNT_ENDPOINT`,
`FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL` are set (the repository variables of the same names); CI never sets them. With
`RECORD_FIXTURES=1` it rewrites `tests/fixtures/recorded.json`, which the other tests replay. Set the endpoints in the shell
from `az`, never in a file. It costs about 0.07 € of Document Intelligence and a few cents of model and Prompt Shields calls.

## Estate checked in phase 0 (2026-10-30, names and states only)

- **GitHub:** public repository with issues and projects, no wiki or discussions, three merge methods, branches kept; ruleset
  `protect-main` (deletion, non_fast_forward, pull_request with 0 approvals, no bypass); environments `staging` (branch `main`),
  `production` (the author as reviewer, tags `v*`) and `github-pages`; Dependabot alerts and security updates, secret scanning
  and push protection on; Pages `build_type: workflow`. CodeQL default setup is enabled after the first PR with code: phase 1
  checks it. Secrets `AZURE_CLIENT_ID` (both environments), `AZURE_CLIENT_ID_PR`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
  `ALERT_EMAIL_ADDRESS`; variables `ACR_NAME`, `SHARED_RESOURCE_GROUP`, `FOUNDRY_ACCOUNT_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`,
  `FOUNDRY_MODEL`.
- **Azure:** `rg-folium-stg-swc` and `rg-folium-prod-swc` in `swedencentral`, tagged `project`, `environment`, `owner`, empty; the
  twelve providers registered. CI principals `gh-product-finance-folium-staging` (credentials `github-staging` and
  `github-pull-request`) and `-production` (`github-production`), no secrets or certificates, with every role of the build
  prompt's identity table and both RBAC Administrator conditions limited exactly to their role lists.
- **Shared base** in `rg-aiplatform-shared-swc` (read, never changed from here): Foundry account `fdry-aiplatform-shared-swc`
  (AIServices S0, local auth off) with project `proj-aiplatform-shared`; deployment `gpt-5-mini` `2025-08-07`, Global Standard,
  100K TPM and 100 RPM, `NoAutoUpgrade`, guardrail `guardrail-chat` (custom, based on `Microsoft.DefaultV2`); registry
  `craiplatformshared` (Basic, admin user off); workspace `log-aiplatform-shared-swc`.
- **Quotas:** `gpt-5-mini` Global Standard 500K TPM in the region, 100K used. Document Intelligence S0: 15 analyze and 50 get
  requests per second per resource, shared by every product on the account. Cosmos DB, Service Bus, Storage and Key Vault: no
  account in the subscription yet, the region open to Cosmos DB, every name in the build prompt available, no soft-deleted vault.
  Container Apps managed environments: 15 in the region, none used, so the two environments of the build prompt's
  `Environments` table fit as designed.

## Decisions taken in phase 0

- **Dependencies.** `requirements.txt` holds what the image runs; `requirements-dev.txt` adds lint, types, tests, load tests and
  the synthetic-data tools. The whole set was installed together on Python 3.12 and `pip check` passed. Later phases add what
  they import first.
- **Dependabot** watches `pip` (the `agent-framework-*` packages grouped, because the integrations require a matching
  `agent-framework-core`), `github-actions` and `docker`. `npm` is added in phase 5 with `web/package.json`.
- **CI** runs one Python job; the web job arrives in phase 5 and the Bicep job in phase 6.
- **The `Dockerfile`** is the runtime image; it is built from phase 6, when `app/` exists, and phase 5 adds the web build stage.
- **Process maps.** One spec, `demo-kit/projects/product-finance-folium/diagrams/src/fol_product_diagrams.py` in the portfolio,
  draws each map with the portfolio's diagram engine and writes the BPMN 2.0 XML from the same coordinates. Both files validate
  against the OMG schema. The step times the client gave add up to 9 to 19 minutes per invoice, the figure used everywhere.

## Decisions taken in phase 1

- **Plain values, evidence apart.** `CanonicalInvoice` holds values only: it is what the rules check, what the export writes,
  what the ground truth records and what the normalizer returns as `response_format` (an all-optional Pydantic model, guide 5.3).
  Confidence and source per field arrive in phase 2 as a separate map keyed by field path, so no rule has to unwrap a value and
  the model is never asked for a confidence it cannot know.
- **Tax lines.** Document Intelligence's `TaxDetails` gives only `Amount` and `Rate` (invoice schema 2024-11-30, verified
  2026-10-30), and the invoice model has no withholding field. So `TaxLine.base` is optional and `irpf` is the normalizer's to
  fill; `tax_line_mismatch` runs only when the base is known. A tax line or line item needs its rate and amount: the phase 2
  mapping builds one only when both are read, and otherwise leaves a `missing_field` to the rules.
- **Duplicates are a pure function.** `duplicates(invoice, others)` decides exact and probable; phase 4's Cosmos query only
  fetches the candidates (same hash or same vendor tax ID). The vendor is the tax ID; when phase 2 matches a vendor by name, the
  matched vendor's tax ID must feed this comparison, or an invoice without a readable tax ID is checked by hash only.
- **Normalisation in the model.** Tax IDs drop spaces and the separators `- . / ,` (not `+` or `*`, which old Irish VAT numbers
  use) and a leading `ES`; every text field is trimmed. Pydantic does not validate `model_copy(update=)` or attribute assignment,
  so phase 4 applies corrections through `model_validate`.
- **Synthetic data.** The vendor master (40 vendors, 6 of them sole traders with IRPF, 4 in the EU, 1 billing in USD), the
  catalogue and the page templates are data in `data/`; the vendor master was generated once with valid checksums and IBANs.
  `ops/make_invoices.py` renders digital PDFs with reportlab (`invariant=True`) and scans with Pillow, drawn with reportlab's
  bundled Bitstream Vera fonts, which cover every character in the data (Pillow's default font lacks the accented ones). Output
  is byte-identical across runs and across file names, so the same-file duplicates are re-rendered, not copied. Issue dates
  follow the sample index and a vendor never repeats within three samples, so the planted findings are the only findings for
  any seed: checked on 3,000 seeds, and on 200 in the suite.
- **Known limits of REQ-04 as specified,** for `RESPONSIBLE_AI.md` and the evaluation: VAT rounded per line can exceed 0.01,
  recargo de equivalencia and 1 % or 2 % IRPF are flagged as invalid rates, discounts and suplidos break the arithmetic rules, and
  invoice numbers that restart every year without the year can look like exact duplicates. Each becomes a finding for the lead,
  never a silent pass.
- **CodeQL** default setup was found `not-configured` on 2026-10-30 with Python on `main`; the enable command went to the author
  with phase 1. Dependabot PR #2 (base image Python 3.12 to 3.15) is not for merging; `dependabot.yml` now ignores minor and
  major Python updates of the image.

## Decisions taken in phase 2

- **The workflow** (`app/workflow.py`, ADR-001): one graph per invoice, named `invoice-<id>`, built per run. A detected attack
  skips `normalize` through a conditional edge. `review` pauses with `request_info`; its response handler records corrections,
  re-runs the REQ-04 rules, and approves, rejects (lead with a reason) or asks the lead again. A clerk's approval of an invoice
  with an open finding never approves it. The workflow's dependencies come in `Services` (analysis by invoice id, shield,
  normaliser, vendor master, duplicate candidates, checkpoint storage): phase 4 wires Blob, Cosmos DB and the clients there.
- **Resume** picks, among the invoice's checkpoints at the highest `iteration_count`, the one whose pending requests hold the
  request id. A run writes seven checkpoints up to the review and nine once approved, two of them at the same iteration, so
  neither the iteration count nor the timestamp alone can pick it. `CHECKPOINT_TYPES` is the allow-list that the file and
  Cosmos DB storages need for the restricted unpickler.
- **One agent** (ADR-002): the mapping reads every field it can, and turns a negative `TaxDetails` line into the IRPF
  withholding. The `Normalizer` fills only empty fields and the taxable base of each tax line it read; every value must be
  printed in the document, or it becomes a `rejected_model_value` finding. Lines labelled IBAN and IBAN-shaped strings are
  redacted before the call. A `ChatClientException` keeps the mapping and adds `model_unavailable`. Options: `store` off,
  reasoning effort `minimal`, `timeout` 15 s per attempt (passed through to the OpenAI SDK, which retries twice), `max_tokens`
  1,500 for the normaliser and 800 for the assistant.
- **Vendor matching** is deterministic, in `app/rules.py`: tax ID first, then the name without case, accents or punctuation.
  The matched vendor's tax ID feeds the duplicate check, so an invoice with a misread or missing tax ID is still compared.
- **Evidence:** every value read carries the confidence, page and polygon of its Document Intelligence field; the currency takes
  the total's. Values the model filled get confidence 0, so the review card always highlights them. Currency amounts are rounded
  to cents.
- **The assistant** reads through a `Catalog` protocol with `find` and `get` only; its tools never return the IBAN or the
  evidence. Phase 4 implements the catalogue on Cosmos DB and passes `CosmosHistoryProvider` on `conversations`.
- **Tests replay recordings.** `tests/doubles.py` has a `BaseChatClient` that replays recorded answers and records what it was
  sent, and runs the workflow in a child process that the resume test kills before the answer. The fixtures hold, per
  invoice, the analysis (API version, model, content, pages, documents), the shield verdict, the model's answer and the model
  version; nothing identifies the subscription.
- **Live results (2026-10-31, eight synthetic invoices):** the mapping equals the ground truth on every field except the tax
  bases and the 0 % VAT line of the EU invoice; with the normaliser, all six invoices it saw equal the ground truth. Prompt
  Shields flagged both injected invoices, the Spanish one included. The live test (eight invoices, one resume and one assistant
  question) took 87 to 89 s from this machine, Azure CLI token acquisition included; phase 7 measures REQ-11 in staging. Document Intelligence, Prompt Shields and `gpt-5-mini` answer the
  operator's Azure CLI identity with the roles it already holds; a single `PermissionDenied` from Document Intelligence on the
  first call that morning did not reproduce later with the same code and credential.

## Verified names (installed wheels, 2026-10-30 and 2026-10-31)

| Package | Name |
|---|---|
| `agent-framework-core` 1.23.0 | `Agent`, `tool`, `Executor`, `handler`, `response_handler`, `executor`, `WorkflowBuilder(start_executor=, checkpoint_storage=, name=)`, `WorkflowContext.request_info(request_data, response_type, *, request_id=None)`, `WorkflowEvent`, `Message`, `Content`, `FunctionMiddleware`, `evaluate_workflow`, `evaluate_agent`, `LocalEvaluator`, `evaluator` |
| `agent-framework-foundry` 1.15.0 | `agent_framework.foundry.FoundryChatClient`, `FoundryEvals` |
| `agent-framework-azure-cosmos` 1.0.0b261015 | `agent_framework_azure_cosmos.CosmosCheckpointStorage`, `CosmosHistoryProvider` (`agent_framework.azure_cosmos` does not import) |
| `azure-ai-documentintelligence` 1.0.2 | `azure.ai.documentintelligence.aio.DocumentIntelligenceClient` |
| `azure-ai-contentsafety` 1.0.0 | `azure.ai.contentsafety.aio.ContentSafetyClient.send_request`; no Prompt Shields method |
| `python-stdnum` 2.2 | `stdnum.es.nif.is_valid` (DNI, NIE and CIF, with or without `ES`), `stdnum.eu.vat.is_valid` (prefixed EU VAT); typed |
| `pydantic` 2.14.2 | functional `StrEnum("Kind", "a b")` members are typed by mypy 2.4.1 and dumped as strings |
| `reportlab` 5.1.0, `types-reportlab` 5.0.0.20261008 | `Canvas(..., invariant=True)`, fonts in `reportlab/fonts/` |
| `pillow` 13.0.0 | `ImageFont.truetype`, `Image.Resampling.BICUBIC`; PDF save writes no dates when `creationDate=None, modDate=None` |
| `agent-framework-core` 1.23.0 (2026-10-31) | `WorkflowBuilder.add_edge(source, target, condition=)`; `Workflow.run(checkpoint_id=, responses=)`; `WorkflowCheckpoint.iteration_count`, `.pending_request_info_events` (iteration not unique since 1.13.0); `FileCheckpointStorage(path, allowed_checkpoint_types=)`; `BaseChatClient._inner_get_response`; `chat_middleware`; `ChatClientException` wraps OpenAI errors, `APITimeoutError` included; unknown chat options such as `timeout` reach the SDK call |
| `agent-framework-foundry` 1.15.0 (2026-10-31) | `FoundryChatClient` reads `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`; the answer's `raw_representation.model` is `gpt-5-mini-2025-08-07` |
| `azure-ai-documentintelligence` 1.0.2 (2026-10-31) | `begin_analyze_document(model_id, IO[bytes], locale=, content_type="application/octet-stream")`; `DocumentField.type`, `value_currency.currency_code`; `TaxDetails.Rate` is a string |
| Prompt Shields `2024-09-01` (Learn, 2026-10-31) | `POST /contentsafety/text:shieldPrompt` through `ContentSafetyClient.send_request` with the path relative to `/contentsafety`; prompt up to 10,000 characters, up to five documents totalling 10,000; an empty `userPrompt` is accepted; trained mainly on English |
