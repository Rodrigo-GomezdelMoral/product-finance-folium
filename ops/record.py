import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

RUNS = Path(__file__).parent.parent / "web" / "src" / "demo" / "runs"
http = httpx.Client(base_url=os.environ.get("FOLIUM_URL", ""), timeout=180)
http.headers["Authorization"] = f"Bearer {os.environ.get('FOLIUM_TOKEN', '')}"
exchanges: list[dict[str, Any]] = []


def call(method: str, path: str, **sent: Any) -> httpx.Response:
    start, response = time.perf_counter(), http.request(method, path, **sent)
    item = {"method": method, "path": path, "status": response.status_code}
    item["ms"] = round(1000 * (time.perf_counter() - start))
    kind = response.headers.get("content-type", "")
    if "json" in kind:
        item["json"] = response.json()
    elif kind.startswith("text/"):
        item |= {"text": response.text, "type": kind}
    elif response.content:
        item |= {"base64": base64.b64encode(response.content).decode(), "type": kind}
    exchanges.append(item | ({"request": sent["json"]} if path.endswith("/review") else {}))
    return response


def show(key: str) -> dict[str, Any]:
    while (found := call("GET", f"/api/invoices/{key}").json())["status"] in ("queued", "processing"):
        time.sleep(2)
    call("GET", f"/api/invoices/{key}/original")
    return dict(found)


def record(args: argparse.Namespace) -> Path:
    me, ids = http.get("/api/me").raise_for_status().json(), [args.invoice] if args.invoice else []
    if args.kind == "upload":
        files = [("files", (path.name, path.read_bytes())) for path in args.files]
        ids = [item["id"] for item in call("POST", "/api/invoices", files=files).raise_for_status().json()]
    if args.kind == "ask":
        call("POST", "/api/chat", json={"message": args.prompt}).raise_for_status()
    for key in [os.urandom(8).hex()] * 2 + [os.urandom(8).hex()] if args.kind == "export" else []:
        call("POST", "/api/exports", headers={"Idempotency-Key": key})
    shown = [show(invoice_id) for invoice_id in ids]
    for review in map(json.loads, args.review):
        at, changes = review.pop("at", 0), review.pop("set", None)
        data = {"data": shown[at]["data"] | changes} if changes else {}
        call("POST", f"/api/invoices/{ids[at]}/review", json=review | data).raise_for_status()
    user = {"name": "Accounting lead" if "Invoice.Approve" in me["roles"] else "Accounts clerk", "roles": me["roles"]}
    run = {"title": args.title, "prompt": args.prompt, "kind": args.kind, "files": [path.name for path in args.files]}
    run |= {"invoice": args.invoice, "user": user, "recorded": time.strftime("%Y-%m-%d"), "exchanges": exchanges}
    text = json.dumps({key: value for key, value in run.items() if value}, ensure_ascii=False)
    (out := RUNS / f"{args.name}.json").write_text(text.replace(me["name"] or user["name"], user["name"]), "utf-8")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record one run of the deployed Folium for the published demo.")
    for argument in ("name", "kind", "title", "prompt"):
        parser.add_argument(argument)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--invoice")
    parser.add_argument("--review", action="append", default=[], help='JSON such as {"at": 0, "action": "approve"}')
    print(record(parser.parse_args()))
