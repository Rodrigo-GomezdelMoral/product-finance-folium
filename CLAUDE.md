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
  Files: <n>/90   Python: <n>/1450   Tests: <n>/700   Bicep: <n>/490   TS: <n>/800   Comments: <n>/5
  Verified: ruff ✓  mypy ✓  pytest ✓  budget ✓  <phase checks>
  Requirements: REQ-xx <test> <live evidence or "local only"> · ...
  Guidance: <syllabus sections> · <Well-Architected codes>
  Publish with: ../_scripts/product-finance-folium/publish-<branch>.sh
  ```

  The counts come from `python -c "from tests.test_budget import budget_counts; print(budget_counts())"`.
- **Identity is the author's.** Roles, federated credentials, app registrations and app-role assignments go in
  `../_scripts/product-finance-folium/<nn>-<what>.sh`; write the script and stop. Phase 3 wrote `02-required-checks.sh` and phase 6
  `03-shared-deployments.sh`, so the sign-in script of phase 7 is `04-signin.sh`.
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
3. **Budgets, enforced by `tests/test_budget.py`** (non-empty lines): Python in `app/ eval/ load/ ops/` at most 1,450 (the
   build prompt's 1,400, raised by the author on 2026-10-31 for `load/locustfile.py`, `ops/record.py` and the load doubles); tests
   at most 700; Bicep at most 490; TypeScript under 800; files at most 90, excluding `docs/`, `data/`, `eval/datasets/`,
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

The emulators run with `docker compose -f ops/compose.yaml up -d`: the Cosmos DB emulator (vNext, preview), Azurite and the
Service Bus emulator with its SQL Server. Set `MSSQL_SA_PASSWORD` to a local password and `ACCEPT_EULA=Y` (the emulators'
licences) in the shell, never in a file. The app reads `COSMOS_ENDPOINT`, `COSMOS_KEY` (the emulator's published key; never set
in Azure), `STORAGE` and `SERVICEBUS` (connection strings locally, the account URL and the namespace in Azure);
`python -m ops.seed` creates the database, containers and blob containers when a key is set, and loads the vendor master. The
suite runs on an in-memory store; the same API flows were run against the emulators on 2026-10-31 (see phase 4).

The web client, from `web/`: `npm ci`, then `npm run build` (type check and build). The Playwright suite runs on a demo build
with the test runs: copy `e2e/runs.json` to `src/demo/runs/e2e.json`, run `VITE_DEMO_MODE=true npx vite build` and `npm test`,
then delete the copy, which is never committed (`src/demo/runs/` holds only runs recorded from staging).

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
  `Environments` table fit as designed. Wrong: ARM preflight in phase 7 found the limit is 1 in the region, taken by
  another product, and 5 in `spaincentral` (ADR-013).

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

## Decisions taken in phase 3

- **The dataset is committed** (`eval/datasets/`, 3.7 MB): the invoices, their hashes and the Document Intelligence cache stay
  fixed when Pillow or reportlab change. `full.jsonl` and `smoke.jsonl` name each suite's invoices and questions;
  `tests/test_eval.py` checks the ground truth against `make_invoices.build(2026)`.
- **The gate** (`eval/run.py`, `eval/evaluators.py`): Document Intelligence cached by file hash in `.cache/di/`, Prompt Shields
  and the model live, four invoices at a time with duplicates after their originals, the assistant over the run's own
  invoices. `possible_injection` on an injected invoice is neutral for the finding metrics; shield detection is reported apart.
  A metric passes at its threshold within its tolerance of the baseline, or, when the baseline is an explained miss below the
  threshold, while it does not get worse. The judge's report URL is never read; an `openai.APIError` from the judge fails the
  gate without stopping the run (`openai` and `pyyaml` are pinned in `requirements-dev.txt` because `eval/` imports them).
- **`eval.yml`** runs on every pull request: `scope` reads the changed paths without Azure, and `evaluate` (smoke suite,
  `AZURE_CLIENT_ID_PR`) is skipped, which reports success, unless an evaluated path changed (the specified ones plus
  `app/extract.py`, `models.py`, `rules.py`, `data/` and the generator) or `scope` failed. `full` runs on demand from `main`
  in the `staging` environment. A conditional `environment` expression was not verified, hence two jobs.
  `../_scripts/product-finance-folium/02-required-checks.sh` makes `python` and `evaluate` required checks.
- **Experiment 001** kept the normaliser and narrowed it: `normalizer_v2` and `FILLABLE` limit it to `tax_lines` and `irpf`,
  after v1 filled `inv-043`'s missing vendor tax ID with the customer's printed NIF. The cross-check is amounts only.
- **The assistant** (`assistant_v2`): `find_invoices` lists the finding kinds and returns each invoice's findings; citations of
  numbers that start with `INV-` are spelled out with examples outside the dataset.
- **Judge alignment:** `builtin.groundedness` read `[INV-…]` citations as wrong numbers (2 of 5 on correct answers); every item's
  context now starts with one sentence stating the convention.
- **A vacuous test found:** `tool.invoke` returns `Content` items, so `str()` of the result never held the IBAN; the test now
  joins `item.text`.
- **Measured (2026-10-31):** smoke 24 model calls, 0.018 € of model and judge tokens, about 75 s; full 97 calls, 0.069 €, about
  4 minutes. The shared account also serves other sessions, so its metrics cannot attribute a run.

## Decisions taken in phase 4

- **The API** (`app/main.py`) takes the principal only from `X-MS-CLIENT-PRINCIPAL`, which external requests cannot set (Learn,
  Container Apps authentication, 2026-07-08); no header is 401, no role is 403. Roles are the claims typed `roles` or the
  header's `role_typ`; the timeline records the `name` claim; conversations belong to a hash of the object id.
- **The store** (`app/store.py`) keeps a `Record`: the invoice plus its file name, type, pending review request and export batch.
  New documents are create-only and every replace carries the ETag; audit entries are created once as `<invoice id>-<nnn>`;
  originals are written once with their SHA-256 as metadata. The request id given to `resume` is the stored one, never the
  client's, and only for an invoice in `ready` or `with_lead`. The same `Store` is the assistant's catalogue.
- **Upload:** magic bytes decide the type (415 otherwise), more than 20 files or one over 10 MB is 413, and an exact hash match
  is flagged at once. Ids are the upload time to the microsecond, the index in the batch and a random byte, so "uploaded
  before" is an id comparison.
- **Duplicates under concurrency:** candidates are earlier uploads with the same hash or vendor, and the check waits, up to
  20 s, while an earlier upload of the last five minutes is still queued or processing, and then raises, so the message is
  retried rather than the invoice cleared. Without it, a re-sent invoice processed next to its original in the same batch is
  missed; `test_duplicate_blocks_export` processes both at once.
- **The consumer** (`app/worker.py`): four receivers (ten since phase 7), peek-lock, locks renewed up to 300 s. An invoice is claimed from `queued`
  with its ETag; a message for an invoice past `processing` is completed without work. Azure SDK, workflow, timeout and data
  errors (`ValueError`, `KeyError`, `ArithmeticError`) abandon the message, and a failed settlement is left to the lock's
  expiry; the fifth delivery (`delivery_count` 4: it starts at 0, checked on the emulator) marks the invoice `failed`
  with the error type and dead-letters the message. A stopped consumer turns `/healthz` into 503 for the liveness probe.
- **Export:** the batch id is the first 16 hex characters of the SHA-256 of `Idempotency-Key`. The first request writes the
  batch, with the approved invoices of that moment, create-only in `exports`; every request with the key then claims only
  those invoices with their ETag and writes the files from the batch's members, so retries and concurrent calls agree, two
  keys never share an invoice, and a retry completes a half-written batch. CSV with one row per tax line, the JSON layout, no
  IBAN.
- **Resume** now takes, among the checkpoints whose pending requests hold the stored request id, the one with the highest
  iteration. The phase 2 rule (only checkpoints at the highest iteration overall) left an invoice unreviewable when the save
  after a successful resume failed. Exactly once is the API's: the request id comes from the stored record, which changes on
  every saved decision, and the save carries the ETag; a second approval gets 409.
- **Upload:** if storing or queuing fails, the invoices already stored are marked `failed`, so none waits in `queued` forever.
- **Erasure** (`ops/erase.py`): sole traders only, and only when every invoice was issued before the fiscal year six years
  back. The vendor's name, tax ID, address and IBAN are replaced in the invoice, its file name and its audit entries (the one
  exception to create-only, run by an operator), its workflow checkpoints and the original are deleted, the vendor leaves the
  vendor master only when every invoice was saved, and an `erased` step records who and when. A rerun continues where it
  stopped. Export files and blob versions expire through lifecycle rules in phase 6 rather than being rewritten.
- **Telemetry:** KPI events are logs with `microsoft.custom_event.name`, which the exporter sends as `customEvents`; logs are
  never trace-sampled (`enable_trace_based_sampling_for_logs=False`, also the 1.8.11 default) while traces keep the default
  limit of 5 per second. There is no local Application Insights, so the KQL check of KPI events moves to phase 7:
  `customEvents | where name in ("invoice_uploaded", "invoice_ready", "invoice_approved", "field_corrected",
  "invoice_exported", "feedback") | summarize count() by name`.
- **Resilience:** an Azure SDK error after the SDK's own retries is a 503 with `Retry-After: 10`; a model failure in the chat
  ends the stream with a sentence.
- **Defect found by the emulators:** an invoice read back from Cosmos DB carries pydantic's `TzInfo`, which the restricted
  unpickler of `CosmosCheckpointStorage` refused, so no review could resume. `CHECKPOINT_TYPES` allows it, and the API tests
  now use `FileCheckpointStorage`, which pickles, so CI catches the class of error.
- **Review:** one independent review of the phase found seven defects, all fixed above (consumer errors, the duplicate wait's
  timeout, resume after a lost save, erasure of checkpoints and file names and its rerun, queued orphans, same-key exports).
  The audit trail is read in id order.
- **Emulator run (2026-10-31):** the API tests against Cosmos DB vNext, Azurite and Service Bus with the real consumer passed,
  before and after the review fixes (the upload test's last line reads statuses that a real queue is still processing); `CosmosHistoryProvider` saved and listed a conversation; the app started with `uvicorn`, took an upload, retried
  it five times against an unreachable model endpoint, marked it `failed` and dead-lettered it.
- **For phase 6:** ADR-003 and ADR-004 record the cross-partition queries on `invoices` (`/id`, bounded by `TOP`), the queue's
  `lockDuration` PT1M and `maxDeliveryCount` 5, a dead-letter alert, lifecycle rules for exports and previous blob versions,
  and the liveness probe on `/healthz`.
- **Budget:** `main.py`, `store.py` and `worker.py` are over their line targets (214, 137 and 67 against 180, 100 and 50);
  the total leaves about 90 Python lines for phases 5 to 8, so the Locust file and `ops/record.py` must stay short, and the
  test budget is full (699 of 700).

## Decisions taken in phase 5

- **One client, two transports.** Every call in `web/src/api.ts` goes through one function: `fetch` in live mode and, in demo
  mode, a replay of the selected run's recorded exchanges (same method and path, in order, the last one repeated for polls,
  after the recorded latency). The interface code is the same in both modes, so the demo is the deployed interface by
  construction. A run file in `web/src/demo/runs/` holds one run or a list: title, prompt (it matches a suggestion), kind
  (`upload`, `ask`, `export`, `open`), user (name and roles), date and exchanges. Phase 8's `ops/record.py` writes this format
  from staging. In a run, a review card enables only the recorded decision and pre-fills its corrections and reason; a card
  the run did not review keeps its decisions disabled.
- **Published before the runs.** The merge of this phase publishes the demo with no runs: the band, the empty state, disabled
  suggestions and "No recorded runs yet". The runs recorded from staging arrive in phase 8; nothing recorded locally is
  published.
- **Test runs.** `web/e2e/runs.json` (four runs) was recorded on 2026-10-31 from the web client in live mode against the real
  API with the test doubles (recorded Azure responses), through an ASGI recorder in a scratch harness that is not committed. CI
  copies it into a demo build for Playwright. Its assistant answer is the test suite's canned answer.
- **Who is signed in** comes from `GET /api/me`, which reads the platform header like every route. Learn's Container Apps
  authentication page (updated 2026-07-08) documents the identity headers and `/.auth/logout`, not `/.auth/me`, which in App
  Service needs the token store. Sign-out is the platform's `/.auth/logout`.
- **Conversations** return their user and assistant turns in `GET /api/conversations`, so the sidebar reopens one without a
  route per conversation.
- **The app serves the built client** from `web/dist` with Starlette's `StaticFiles` (`html=True`), mounted after every route.
  `check_dir=False` lets the app start without a build; without one, an unmatched path answers 500 instead of 404, and a wrong
  method on an API route answers 404 instead of 405, because the mount at `/` takes every unmatched request. Neither costs a
  Python line to change, and the image always has the build. The image builds it in a `node:24.22.2-trixie-slim`
  stage pinned by digest; the image was built and `web/dist` checked inside it on 2026-10-31.
- **Polling:** each invoice card polls `GET /api/invoices/{id}` every 2 s while queued or processing, because processing may
  run on another replica. Its status lines are the timeline's steps with seconds since upload, then "Ready for review in n s".
  The time the review card was open goes to `review_seconds` (handling-time KPI); 👍 and 👎 post `/api/feedback`.
- **Accessibility:** accent text on light backgrounds uses `#4552E0` (5.2:1 on the selection background; `#5764F8` gives 4.0:1
  there and 4.2:1 on the page, below AA for 13 to 15 px text); the success green is for icons only (3.5:1 on white); error text
  sits on white (4.7:1); inputs are bordered in `#626262` for 3:1 non-text contrast; a low-confidence field carries an icon and
  a label, not colour alone; after a decision, focus moves to the card's new status. axe runs with `wcag2a`, `wcag2aa`,
  `wcag21aa` and `wcag22aa` and fails on serious or critical violations.
- **Local live run (2026-10-31):** the web client against the real API with the test doubles, driven by Playwright: batch of
  three ready with their steps, 12 of 64 fields marked below 0.80, a due-date correction in the timeline, approval; a cited
  answer; an exact duplicate where the clerk sees only *Send to lead*; the lead's *Approve* disabled until a reason is given;
  export of two invoices, then 409 *No approved invoices to export*. Phase 7 repeats it in staging.
- **Found while testing:** Chromium's `scrollIntoView` now returns a promise, which React took as an effect's clean-up and
  crashed on; effects use braces. Headless Chromium does not render a PDF in an iframe, so headless screenshots show the
  original's frame empty; desktop browsers render it.
- **Dependencies:** TypeScript 7.0.2 (the native compiler) type-checks as the lint, with no ESLint; `react-markdown` renders
  answers without raw HTML; Inter comes from `@fontsource/inter` (latin, 400 and 600) inside the bundle, so no third-party font
  request. Each package is the latest release at least two weeks old, except Vite 8.3.5 (10 days) and React 19.3.1 (17 days);
  `lucide-react` publishes daily and 1.59.0 is from 2026-10-17.
- **Review:** one independent review of the phase's diff found six defects, all fixed: work started in one thread could
  write into the next one (each thread now has a generation, and the streamed answer is replaced by identity, not position); a
  clerk saw the review form of an invoice waiting for the lead; a failed poll stopped polling (5xx and network errors now retry
  every 10 s and keep the card); the original had no error path and leaked its blob URL after unmount; the queue read the
  newest 100 invoices and filtered them (it now asks the API per status, once the roles are known); and state carried over
  between threads (the thread remounts on each). Also applied: decisions disabled while one is saving, answers render no
  images and only in-page links, card updates refresh the sidebar once a second at most, focus returns to the thread when its
  control disappears, the streamed answer is `aria-busy`, Enter during IME composition does not send, export is offered to
  the lead only, and run files enter only demo builds. Not applied: a Content Security Policy needs a response header from
  the app (Python lines) or an index-time plugin; the vectors it would close are closed in the Markdown renderer.
- **Budget:** Python 1,315 after this phase's six lines (`/api/me`, the turns, the static mount): 85 remain for
  `load/locustfile.py` and `ops/record.py`, whose targets add up to 90. TypeScript 710 of 799.

## Decisions taken in phase 6

- **Infrastructure** (`infra/`, Bicep 0.48.1): `main.bicep` at resource-group scope, five modules (`roles`, `shared`, `data`,
  `monitor`, `app`) and one parameter file per environment that reads the run's values from the environment: `IMAGE_DIGEST`,
  `AUTH_CLIENT_ID`, `REVISION_SUFFIX`, `STABLE_REVISION` (optional) and `ALERT_EMAIL_ADDRESS`. API versions are the newest GA
  in Bicep's type index; `infra/bicepconfig.json` turns on `use-recent-api-versions` and CI's `bicep` job fails on any warning.
  The one exception, `diagnosticSettings@2021-05-01-preview` (the newest version and the only one with `categoryGroup`), is
  suppressed on its line, as in the platform repositories.
- **Role ids without hyphens.** Built-in role definition names are public constants, but the identifier scan flags any GUID.
  `roles.bicep` keeps them as 32 hex characters and `uuid()` formats them, so the scan stays strict with no allow-list. The
  ids come from the platform repositories' verified notes; `what-if` and the first deployment confirm them.
- **No client secret and no Key Vault** (ADR-009): Learn (2026-02-20) makes the secret optional; without it the platform
  uses the implicit flow and an ID token, which carries the app roles. `04-signin.sh` must enable ID tokens, set the
  callback redirect URI and `api://<client id>`, create both app roles with assignment required (`Invoice.Process` for users
  and applications), give the staging CI
  principal `Invoice.Process`, and set `AUTH_CLIENT_ID`, `RESOURCE_GROUP` and `CONTAINER_APP_NAME` per environment.
- **Container Apps:** a workload-profiles environment with the Consumption profile, logs to the shared workspace through a
  diagnostic setting (destination `azure-monitor`, so no workspace key); the app in multiple-revision mode (ADR-005) with an
  HTTP rule (20 concurrent requests) and the queue rule (4 messages per replica, 10 since phase 7) through `id-folium-<env>-scale`, lifecycle
  `None` (ADR-006); startup, liveness and readiness probes on `/healthz`; 0.5 vCPU and 1 GiB.
- **Revisions and traffic.** Each run passes a unique suffix that starts with a letter: `r<run>-<attempt>-<sha7>` in staging,
  `p<run>-<attempt>-<sha7>` in production, `load<run>-<attempt>` for load tests. The Bicep keeps the stable revision at 100 %
  and puts the new one at 0 % behind the `canary` label; the workflows move traffic with `az containerapp ingress traffic set`
  and deactivate the old revision. The image reference is built from the registry's login server at deployment, so no
  registry host is written anywhere.
- **Workbook and alerts** (`monitor.bicep`): nine KQL tiles (four KPIs against target, two SLAs against commitment, the health
  model, KPI events arriving). The worker's `invoice_ready` carries `fields`, not the prompt's `field_count`; the queries use
  `fields`. Alerts exist in production only: three log alerts and one metric alert, about 1.4 €/month.
- **Budgets** start on a fixed 2026-11-01: a start date from `utcNow()` would change on every monthly redeployment, which the
  budgets API may refuse; a future start may be at most three months ahead, a past one within the current month.
- **Shared-base deployments.** `shared.bicep` is a nested deployment in `rg-aiplatform-shared-swc`, which needs
  `Microsoft.Resources/deployments/write` there; RBAC Administrator only reads and writes role assignments. The author's
  `../_scripts/product-finance-folium/03-shared-deployments.sh` creates the custom role *Folium shared-base deployments*
  (`Microsoft.Resources/deployments/*`, assignable only on that group) and gives it to both CI principals.
- **Workflows:** the federated token behind `azure/login` expires within minutes, so `deploy.yml` and `load-test.yml` sign in
  again before each later token request; an unknown app is the only case read as a first deployment; `verify` counts only
  `push` runs of `deploy.yml`; `load-test.yml` posts its status on the commit the stable revision runs (from its suffix),
  drains the queue before reactivating the stable revision, lets the KQL check decide instead of Locust's exit code, and
  uploads only the stats and platform tables, since Locust's failure files can name the host. The first deployment may need
  one rerun while the new role assignments propagate.
- **`load-test.yml` waits for phase 7's code:** `load/locustfile.py`, which picks its shape from `LOAD_SCENARIO` (`normal`,
  `peak`, `soak`, `stress`, `real`), reads the bearer token from `LOAD_TOKEN` and the soak length from `SOAK_MINUTES`; and the
  doubles behind `DOUBLES=load`, honoured only when `ENVIRONMENT=staging`. Python has 85 lines left for those doubles,
  `load/locustfile.py` and `ops/record.py` (targets 45 and 45).
- **Review:** one independent review of the diff found eight defects, all fixed: a startup probe over the maximum failure
  threshold of 10, a verify step that passed on a failed check, expired federated tokens, the missing deployment right on the
  shared group, a transient error read as a first deployment, the stable revision draining the load test through the real
  services, the status posted on the wrong commit, and Locust's exit code as the gate. Also applied: the canary revision
  pinned by name, the fixed budget date, the artifact contents and the documents' `what-if` claims.
- **A test defect fixed:** the pin check read `statuses:` as `uses:`; it now matches `uses:` as a word, on the same line.
- **Not run in this phase:** `what-if` for both environments needs an interactive `az login` (the stored token expired and the
  tenant's security defaults require MFA). `bicep build`, `build-params` and `lint` are clean.

## Decisions taken in phase 7

- **Two publishes from `feature/staging`.** `load-test.yml` runs from `main` and redeploys the staging digest with
  `DOUBLES=load`, so the Locust file and the doubles must be in an image built from `main` before any load test. The first
  publish carries that code and the sign-in fixes; its merge is also the first deployment. The second carries the measured
  results.
- **Budget:** the author raised the Python total from 1,400 to 1,450 on 2026-10-31 for `load/locustfile.py` (45), `ops/record.py`
  (45) and the doubles.
- **The load doubles** (`app/doubles.py`, honoured only when `ENVIRONMENT=staging` and `DOUBLES=load`) replace Document
  Intelligence and the normaliser's model; Prompt Shields, Cosmos DB, Blob Storage and Service Bus stay real. The analysis is
  one recorded invoice (`app/doubles.json`, from `tests/fixtures/recorded.json`) whose vendor is drawn from the vendor master
  by the invoice id, whose issue date moves back by a multiple of 8 days drawn the same way, and whose number is the invoice
  id, so load invoices are neither exact nor probable duplicates of each other. They still wait, like every upload, for any
  earlier upload of the last five minutes that is queued or processing (phase 4's duplicate check). The vendor master must be
  seeded before a load test: `vendors` is read once per replica, and an empty one fails every doubled invoice. Latencies: Document Intelligence 7.5 s (7.4 to 9.6 s for one page, three calls from the operator's machine on
  2026-10-31), the model 4.0 s (the evaluation's p95 with the normaliser, 4.6 to 6.6 s, less 1.5 s without it). The model
  name in the timeline is `load-double`. A local run of the workflow on the doubles took 11.6 s per invoice.
- **`load/locustfile.py`:** one user class uploads one invoice (normal, soak, stress) or a 20-file batch (peak, real) and
  polls each invoice every 2 s; the time from upload to a status past `processing` is a Locust entry `READY invoice`, failed
  when the status is `failed`. A load shape per scenario sets users, spawn rate and length; stress ramps 10 users a minute,
  each uploading once a minute, and stops when the current p95 of `READY` passes 30 s or errors pass 1 % after 100 requests.
  Load invoices are unique bytes behind the PDF magic; the real scenario sends the first 20 dataset PDFs with a unique
  trailing comment. Checked against a local fake API: 20 of 20 ready in the real shape, stress stopping at its threshold.
- **Sign-in** (`04-signin.sh`): `folium-<env>` with ID tokens, `api://<client id>`, access tokens version 2 (their issuer
  matches the platform's `/v2.0` issuer; their audience is the client id, which `allowedAudiences` now lists next to
  `api://<client id>`), `Invoice.Process` for users and applications, `Invoice.Approve` for users, assignment required, the
  staging CI principal as a clerk, the author as a lead in both environments, a `user_impersonation` scope pre-authorized for
  Azure CLI so the operator can call the API with `az account get-access-token`, and the environment variables. A second run
  after the first deployment adds the sign-in redirect URI and the operator's data roles in staging (Cosmos DB Built-in Data
  Contributor, Storage Blob Data Contributor) for the vendor seed, the erasure run and the restore drill.
- **Review before the first publish:** one independent review found no blocking defect. Applied: probable duplicates among
  load invoices (the issue-date spread above), a poll that raised on a non-JSON body and lost its batch's measurements, the
  stress stop read from every request (now uploads and `READY` only), an empty `SOAK_MINUTES`, and ID tokens set again with
  the redirect URI. Open risk, measured by the two load tests below: with 0 to 2 replicas of 4 consumers and about 12 s per doubled invoice, the last
  invoices of a 20-file peak batch can pass 30 s and take the combined p95 over the SLA; ADR-011's fallbacks then apply.
- **The environment and the app in `spaincentral` (ADR-013).** The first staging deployment failed in preflight with
  `MaxNumberOfRegionalEnvironmentsInSubExceeded`: 1 of 1 environments used in `swedencentral` by another product, 0 of 5 in
  `spaincentral`. The author moved only the environment and the app: `appLocation` in `main.bicep` (default `spaincentral`),
  environments `cae-folium-<env>-spc`; resource groups, data, identities, Application Insights and the shared base stay in
  `swedencentral`. Each data call adds the 50 ms round trip (about 1 to 1.5 s per invoice), which the load tests measure.
  Workflows and `04-signin.sh` read the ingress host name from the app, so none of them changes.

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
| `agent-framework-core` 1.23.0 (phase 3) | `EvalItem(conversation, context=)`, `LocalEvaluator(*checks).evaluate(items)` → `EvalResults.per_evaluator`, `.items[].scores`; `@evaluator` resolves `query`, `response` by parameter name; `InMemoryCheckpointStorage`; evaluation is `@experimental` (`EVALS`); `evaluate_agent` takes one `context` for all queries, so the gate builds its items; `FunctionTool.invoke` returns `list[Content]` |
| `agent-framework-foundry` 1.15.0 (phase 3) | `FoundryEvals(client=, evaluators=[FoundryEvals.GROUNDEDNESS])` → `builtin.groundedness` through the OpenAI evals API; an item's score can be `None` |
| `builtin.groundedness` (Learn, page of 2026-08-26) | GA; `response` and `context`, `query` optional; scores 1 to 5, default pass threshold 3 |
| GitHub Actions (docs, 2026-10-31) | a skipped job reports success and does not block a required check; `azure/login` v3 only moves to Node 24; `actions/cache` v6 restore and save inputs unchanged |
| Prompt Shields `2024-09-01` (Learn, 2026-10-31) | `POST /contentsafety/text:shieldPrompt` through `ContentSafetyClient.send_request` with the path relative to `/contentsafety`; prompt up to 10,000 characters, up to five documents totalling 10,000; an empty `userPrompt` is accepted; trained mainly on English |
| `fastapi` 0.162.0, `starlette` 1.10.0 (phase 4) | `UploadFile.size`; form parsing needs `python-multipart` (0.0.32, pinned) |
| `azure-servicebus` 7.15.0 (phase 4) | `get_queue_receiver(queue, auto_lock_renewer=)`, `AutoLockRenewer(max_lock_renewal_duration=)`, `abandon_message`, `dead_letter_message(reason=)`; `delivery_count` is 0 on the first delivery |
| `azure-monitor-opentelemetry` 1.8.11 (phase 4) | `configure_azure_monitor(credential=, logger_name=, enable_trace_based_sampling_for_logs=)`; default sampler 5 traces per second; exporter 1.0.0b58 maps `microsoft.custom_event.name` to `customEvents` |
| `agent-framework-azure-cosmos` 1.0.0b261015 (phase 4) | `CosmosHistoryProvider(container_client=)` on `/session_id`, `list_sessions()`, `get_messages(session_id)`; `CosmosCheckpointStorage(container_client=, allowed_checkpoint_types=)` |
| `agent-framework-core` 1.23.0 (phase 4) | `Agent.run(message, stream=True, session=AgentSession(session_id=))` returns a `ResponseStream` of updates with `.text`; `ChatResponse.from_update_generator` |
| Service Bus emulator 2.0.1 (Learn, page of 2026-08-28) | needs SQL Server 2022; configuration at `/ServiceBus_Emulator/ConfigFiles/Config.json`; `DefaultMessageTimeToLive` at most 1 hour |
| npm packages (2026-10-31) | `react`/`react-dom` 19.3.1, `vite` 8.3.5 (`import.meta.glob(pattern, { eager: true, import: "default" })`), `@vitejs/plugin-react` 6.1.2, `typescript` 7.0.2, `react-markdown` 10.1.0, `@fontsource/inter` 5.3.0 (`latin-400.css`, `latin-600.css`), `lucide-react` 1.59.0 (every icon imported exists), `@playwright/test` 1.64.1, `@axe-core/playwright` 4.14.0 (`new AxeBuilder({ page }).withTags([...]).analyze()`) |
| GitHub Actions (2026-10-31) | `actions/setup-node` v7.1.0 (`node-version`, `cache`, `cache-dependency-path`), `actions/upload-pages-artifact` v5.0.0 (`path`), `actions/deploy-pages` v5.0.1 (output `page_url`) |
| `starlette` 1.10.0 (phase 5) | `StaticFiles(directory=, html=True, check_dir=False)`; an unmatched path reaches the mount and gets 404 |
| Container Apps authentication (Learn, updated 2026-07-08) | identity headers only from the platform; `/.auth/login/aad`, `/.auth/logout`; `/.auth/me` not documented |
| Container Apps (Learn, phase 6, 2026-10-31) | Entra sign-in (updated 2026-02-20): client secret optional, implicit flow returns an ID token only; managed identities (2026-02-13): scale rule `identity` takes a user-assigned resource id, `identitySettings` `lifecycle: None` for scale-rule identities; scaling (2026-05-20): event rules advised with single-revision mode, polling 30 s, cool-down 300 s; no Service Bus role named for the scaler |
| Bicep 0.48.1 types (phase 6) | `Microsoft.App` 2026-07-01, `DocumentDB` 2026-03-15, `Storage` 2026-06-01, `ServiceBus` 2026-01-01, `ManagedIdentity` 2024-11-30, `Insights/components` 2020-02-02, `workbooks` 2023-06-01, `scheduledQueryRules` 2026-03-01, `metricAlerts` 2026-01-01, `actionGroups` 2023-01-01, `Consumption/budgets` 2026-06-01, `CognitiveServices` 2026-07-01, `ContainerRegistry` 2025-11-01, `OperationalInsights` 2026-03-01 |
| Retail Prices API (EUR, `swedencentral`, 2026-10-31) | Service Bus Standard base unit 0.0118 €/h, Premium 0.8162 €/h; Front Door Standard 30.80 €/month base, Premium 290.39 €/month; Defender for Containers 0.0083 € per vCore-hour, 0.2552 € per image; Defender for Cosmos DB 0.0011 € per 100 RU/s-hour |

## Phase 7, second part (2026-11-01)

- **Staging live.** Vendor master seeded with `ops/seed.py` as the operator. Live test through the
  API and the web as the lead: every Must reached its final state (see `docs/OPERATIONS.md`). Cold start 35.3 s to the `202`,
  about 49 s to ready (ADR-011 measurement). Restore drill: Cosmos DB point-in-time restore 656 s; data-plane role assignments
  are not restored; blob version restore 13 s. Advisor: nothing on Folium's groups.
- **First load test (run 41293079362) failed REQ-10 and REQ-11:** p95 ready 41.4 s, availability 98.2 %. Fixed: the shared
  Service Bus sender raced on concurrent first sends (`503`), now behind an `asyncio.Lock`; the gate read one value of a
  multi-line `tsv` row; the assistant's stream repeated its text (the Responses API's `output_text.done` arrives as a
  `merge_mode="replace"` content, now skipped; the `Replay` double emits it too). Open: capacity under 20-invoice batches,
  a decision for the author (receivers per replica, staging replicas, ADR-011 cron rule).
- **Author's decision (2026-11-01):** `CONSUMERS` 10 in `app/main.py` and the queue rule's `messageCount` 10 in `app.bicep`,
  both environments (ADR-003 note: peak CPU 0.13 of 0.5 vCPU, Document Intelligence at 1 to 2 submissions per second); in
  production only, the custom rule `business-hours` (KEDA `cron`, `Europe/Madrid`, `0 8 * * 1-5` to `0 19 * * 1-5`,
  `desiredReplicas` 1, selected by `short == 'prod'`), about 3 to 4 €/month (ADR-011, `docs/cost.md`). Staging keeps scale
  to zero; staging replicas stay at 2. The load test ran again after the merge (below). `what-if` not run: no read-only `what-if`
  from this machine is recorded since phase 6's expired token; `bicep build` and `lint` are clean.
- **Telemetry:** spans are sampled (5 traces per second by default), so model token counts per normalizer call are not
  complete in staging; KPI events are logs and are not sampled.
- **Second load test (run 41299957986, commit `4785e17`) met REQ-10 and REQ-11:** p95 ready 24.2 s and availability 100 %
  over normal, peak and soak; `load-test` set to `success`. No failed request or invoice in any scenario; the two
  dead-lettered messages are run 1's. Peak batch alone 41 s at p95 (56 s in run 1); stress stopped at about 105 users on
  p95, with no error; 20 invoices through the real services 49 s at p95 from the click, 17 s of it the restored revision's
  cold start. Peak CPU 0.18 vCPU, memory 0.49 GB, queue 22, replicas 2. Staging back at zero replicas afterwards.
  `release.yml` reads `load-test` on the released commit, so phase 8 runs the load test on the release candidate.
