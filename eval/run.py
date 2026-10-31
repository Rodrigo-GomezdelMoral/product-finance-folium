import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml
from agent_framework import EvalItem, InMemoryCheckpointStorage, LocalEvaluator, Message
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.ai.contentsafety.aio import ContentSafetyClient
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.identity.aio import DefaultAzureCredential
from openai import APIError

from app import extract
from app.agents import assistant, normalizer
from app.models import Invoice, compact
from app.rules import number_key, squash
from app.workflow import Services, build
from eval.evaluators import Outcome, checks, score
from ops import make_invoices

ROOT = Path(__file__).resolve().parent
DATA, CACHE, RESULTS = ROOT / "datasets", ROOT.parent / ".cache" / "di", ROOT / "results"
GATE: dict[str, Any] = yaml.safe_load((ROOT / "thresholds.yaml").read_text("utf-8"))
CITED = "Answers cite invoices as [INV-<number>]: [INV-A-1] and [INV-INV-2] cite the invoices numbered A-1 and INV-2."
JUDGE, NAMES = FoundryEvals.GROUNDEDNESS, {tax_id: vendor["name"] for tax_id, vendor in make_invoices.VENDORS.items()}


class Catalog(list[Invoice]):
    async def find(self, status: str | None, vendor: str | None, finding: str | None) -> list[Invoice]:
        hits = [i for i in self if status in (None, i.status) and finding in (None, *(f.kind for f in i.findings))]
        return [i for i in hits if squash(vendor or "") in squash(i.data.vendor_name or "")]

    async def get(self, number: str) -> list[Invoice]:
        return [i for i in self if number_key(i.data.invoice_number) == number_key(number)]


def digest(file: str) -> str:
    return hashlib.sha256((DATA / "invoices" / file).read_bytes()).hexdigest()


async def analysis(client: DocumentIntelligenceClient, file: str) -> AnalyzeResult:
    path = CACHE / f"{digest(file)}.json"
    if not path.exists():
        raw = (await extract.analyze(client, (DATA / "invoices" / file).read_bytes())).as_dict()
        kept = {key: raw[key] for key in ("apiVersion", "modelId", "content", "documents")}
        path.write_text(json.dumps(kept | {"pages": [{"pageNumber": page["pageNumber"]} for page in raw["pages"]]}))
    return AnalyzeResult(json.loads(path.read_text("utf-8")))


async def process(samples: list[make_invoices.Sample], services: Services, done: list[Outcome]) -> None:
    gate = asyncio.Semaphore(4)

    async def one(sample: make_invoices.Sample) -> None:
        async with gate:
            started = time.perf_counter()
            result = await build(sample.file, services).run(Invoice(id=sample.file, sha256=digest(sample.file)))
            [request], elapsed = result.get_request_info_events(), time.perf_counter() - started
            done.append(Outcome(sample, request.data.invoice, bool(result.get_outputs()), elapsed))

    for twins in (False, True):
        await asyncio.gather(*(one(sample) for sample in samples if bool(sample.duplicate_of) == twins))


async def main(suite: str, model: bool) -> dict[str, Any]:
    picked = [json.loads(line) for line in (DATA / f"{suite}.jsonl").read_text("utf-8").splitlines()]
    samples = [row for row in make_invoices.build(2026) if suite == "full" or {"file": row.file} in picked]
    questions, done = [item for item in picked if "question" in item], list[Outcome]()
    endpoint, credential = os.environ["FOUNDRY_ACCOUNT_ENDPOINT"], DefaultAzureCredential()
    di, cs = DocumentIntelligenceClient(endpoint, credential), ContentSafetyClient(endpoint, credential)
    CACHE.mkdir(parents=True, exist_ok=True)
    async with credential, di, cs:
        client = FoundryChatClient(credential=credential)

        async def candidates(invoice: Invoice) -> list[Invoice]:
            return [run.invoice for run in done]

        agent, storage = normalizer(client) if model else None, InMemoryCheckpointStorage()
        services = Services(partial(analysis, di), partial(extract.attacked, cs), agent, NAMES, candidates, storage)
        await process(samples, services, done)
        helper, items = assistant(client, Catalog(run.invoice for run in done)), list[EvalItem]()
        for question in questions:
            reply = await helper.run(question["question"])
            outputs = [str(c.result) for m in reply.messages for c in m.contents if c.type == "function_result"]
            conversation = [Message("user", [question["question"]]), *reply.messages]
            items.append(EvalItem(conversation, context="\n".join([CITED, *outputs])))
        secrets = {compact(str(value)) for row in samples for value in (row.canary, row.invoice.iban) if value}
        local = await LocalEvaluator(*checks(questions, secrets)).evaluate(items)
        try:
            judged = await FoundryEvals(client=client, evaluators=[JUDGE]).evaluate(items, eval_name=f"folium-{suite}")
            grounded = [s.score for item in judged.items for s in item.scores if s.score is not None]
            status = f"{judged.status}, {len(grounded)} of {len(items)} scored"
        except APIError as error:
            grounded, status = [], f"failed: {type(error).__name__} {getattr(error, 'status_code', '')}"
    metrics, misses = score(done)
    passed = {name: count["passed"] for name, count in local.per_evaluator.items()}
    metrics["injection_effect"] += len(items) - passed.get("no_leak", len(items))
    metrics |= {"groundedness": round(fmean(grounded), 2) if grounded and len(grounded) == len(items) else 0.0}
    metrics |= {"citation_correctness": round(passed.get("citation_correct", 0) / max(len(items), 1), 4)}
    base, rules = GATE["baseline"].get(suite, {}), GATE["thresholds"]
    verdicts = {name: verdict(metrics[name], rule, base.get(name)) for name, rule in rules.items()}
    rows = zip(questions, items, local.items, strict=True)
    answers = {q["id"]: {"text": i.response, "failed": [s.name for s in r.scores if not s.passed]} for q, i, r in rows}
    report = {"suite": suite, "date": datetime.now(UTC).isoformat(timespec="seconds"), "normalizer": model}
    report |= {"invoices": len(done), "questions": len(items), "judge": status, "passed": all(verdicts.values())}
    return report | {"metrics": metrics, "verdicts": verdicts, "baseline": base, "misses": misses, "answers": answers}


def verdict(value: float, rule: dict[str, float], base: float | None) -> bool:
    drop = 0.0 if base is None else round(value - base if "max" in rule else base - value, 6)
    within = rule.get("min", value) <= value <= rule.get("max", value) or (base is not None and drop <= 0)
    return within and drop <= rule.get("tolerance", 0.0)


def markdown(report: dict[str, Any]) -> str:
    lines = [f"### Evaluation, {report['suite']} suite: {'passed' if report['passed'] else 'failed'}", ""]
    lines += [f"{report['invoices']} invoices, {report['questions']} questions, judge {report['judge']}.", ""]
    lines += ["| Metric | Value | Gate | Baseline | Pass |", "|---|---|---|---|---|"]
    for name, value in report["metrics"].items():
        gate = " ".join(f"{k} {v}" for k, v in GATE["thresholds"].get(name, {}).items())
        mark = "✓✗"[not report["verdicts"][name]] if gate else ""
        lines.append(f"| {name} | {value} | {gate} | {report['baseline'].get(name, '')} | {mark} |")
    return "\n".join([*lines, "", *[f"- {miss}" for miss in report["misses"][:30]]]) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Folium's evaluation gate against the shared Azure AI services.")
    parser.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--no-normalizer", dest="model", action="store_false", help="ablation: the mapping alone")
    args = parser.parse_args()
    result = asyncio.run(main(args.suite, args.model))
    RESULTS.mkdir(exist_ok=True)
    name = args.suite + ("" if args.model else "-no-normalizer")
    (RESULTS / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", "utf-8")
    (RESULTS / "report.md").write_text(markdown(result), "utf-8")
    raise SystemExit(0 if result["passed"] else 1)
