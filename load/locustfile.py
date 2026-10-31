import os
import time
from pathlib import Path
from uuid import uuid4

from locust import HttpUser, LoadTestShape, constant_pacing, task

SCENARIO, TOKEN = os.environ.get("LOAD_SCENARIO", "normal"), os.environ.get("LOAD_TOKEN", "")
SHAPES = {"normal": (5, 5.0, 300), "soak": (5, 5.0, 60 * int(os.environ.get("SOAK_MINUTES") or 30))}
SHAPES |= {"peak": (3, 1 / 40, 300), "real": (1, 1.0, 240), "stress": (120, 1 / 6, 1200)}
READY = {"request_type": "READY", "name": "invoice", "response_length": 0, "context": {}}
BATCH = 20 if SCENARIO in ("peak", "real") else 1
REAL = sorted((Path(__file__).parent.parent / "eval" / "datasets" / "invoices").glob("*.pdf"))[:BATCH]


def invoice(index: int) -> bytes:
    original = REAL[index].read_bytes() if SCENARIO == "real" else b"%PDF-1.7\n"
    return original + f"\n%{uuid4().hex}\n".encode()


class Clerk(HttpUser):
    wait_time = constant_pacing(60 if BATCH == 1 else 3600)

    def on_start(self) -> None:
        self.client.headers["Authorization"] = f"Bearer {TOKEN}"

    @task
    def upload(self) -> None:
        files = [("files", (f"load-{index}.pdf", invoice(index), "application/pdf")) for index in range(BATCH)]
        start, response = time.monotonic(), self.client.post("/api/invoices", files=files)
        pending = {item["id"] for item in response.json()} if response.status_code == 202 else set()
        while pending:
            time.sleep(2)
            for invoice_id in sorted(pending):
                reply = self.client.get(f"/api/invoices/{invoice_id}", name="/api/invoices/[id]")
                status = reply.json().get("status") if reply.status_code == 200 else None
                if status not in ("queued", "processing", None):
                    pending.discard(invoice_id)
                    ms, error = 1000 * (time.monotonic() - start), RuntimeError(status) if status == "failed" else None
                    self.environment.events.request.fire(**READY, response_time=ms, exception=error)


class Shape(LoadTestShape):
    def tick(self) -> tuple[int, float] | None:
        users, rate, seconds = SHAPES[SCENARIO]
        if self.runner is None or time.perf_counter() - self.start_time > seconds:
            return None
        ready, uploads = self.runner.stats.get("invoice", "READY"), self.runner.stats.get("/api/invoices", "POST")
        late = (ready.get_current_response_time_percentile(0.95) or 0) > 30000
        failing = any(entry.num_requests > 100 and entry.fail_ratio > 0.01 for entry in (ready, uploads))
        return None if SCENARIO == "stress" and (late or failing) else (users, rate)
