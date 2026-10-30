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

## Verified names (installed wheels, 2026-10-30)

| Package | Name |
|---|---|
| `agent-framework-core` 1.23.0 | `Agent`, `tool`, `Executor`, `handler`, `response_handler`, `executor`, `WorkflowBuilder(start_executor=, checkpoint_storage=, name=)`, `WorkflowContext.request_info(request_data, response_type, *, request_id=None)`, `WorkflowEvent`, `Message`, `Content`, `FunctionMiddleware`, `evaluate_workflow`, `evaluate_agent`, `LocalEvaluator`, `evaluator` |
| `agent-framework-foundry` 1.15.0 | `agent_framework.foundry.FoundryChatClient`, `FoundryEvals` |
| `agent-framework-azure-cosmos` 1.0.0b261015 | `agent_framework_azure_cosmos.CosmosCheckpointStorage`, `CosmosHistoryProvider` (`agent_framework.azure_cosmos` does not import) |
| `azure-ai-documentintelligence` 1.0.2 | `azure.ai.documentintelligence.aio.DocumentIntelligenceClient` |
| `azure-ai-contentsafety` 1.0.0 | `azure.ai.contentsafety.aio.ContentSafetyClient.send_request`; no Prompt Shields method |
