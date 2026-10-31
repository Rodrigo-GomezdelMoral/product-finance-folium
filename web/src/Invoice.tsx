import { CircleAlert, CircleCheck, LoaderCircle, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, DEMO, LEAD, recorded, type Invoice, type User } from "./api";

const WORKING = ["queued", "processing"];
const REVIEWABLE = ["ready", "with_lead"];
const WORDS: Record<string, string> = { tax_lines: "tax line", line_items: "line", irpf: "IRPF", iban: "IBAN", sha256: "SHA-256" };
const DONE: Record<string, string> = {
  approved: "Approved",
  rejected: "Rejected",
  exported: "Exported",
  with_lead: "Waiting for the accounting lead",
  ready: "Ready for review",
  failed: "Processing failed; upload the invoice again",
};

export const words = (text: string) => {
  const out = text.split(".").map((part) => (/^\d+$/.test(part) ? String(+part + 1) : (WORDS[part] ?? part)));
  return out.join(" ").replaceAll("_", " ").replace("tax id", "tax ID").replace(/^./, (first) => first.toUpperCase());
};

const text = (value: unknown) => (value == null ? "" : String(value));
const leaves = (value: unknown, path = ""): [string, unknown][] =>
  value && typeof value === "object"
    ? Object.entries(value).flatMap(([key, item]) => leaves(item, path ? `${path}.${key}` : key))
    : [[path, value]];

function rebuild(base: Record<string, unknown>, form: Record<string, string>) {
  const data = structuredClone(base) as Record<string, any>;
  for (const [path, value] of Object.entries(form)) {
    const keys = path.split(".");
    const parent = keys.slice(0, -1).reduce((node, key) => (node[key] ??= {}), data);
    parent[keys.at(-1)!] = value.trim() || null;
  }
  if (data.irpf && !data.irpf.rate && !data.irpf.amount) data.irpf = null;
  return data;
}

async function sha256(blob: Blob) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function Original({ invoice }: { invoice: Invoice }) {
  const [view, setView] = useState({ url: "", verified: false, type: "" });
  useEffect(() => {
    let url = "";
    let alive = true;
    api.original(invoice.id).then(
      async (blob) => {
        const verified = (await sha256(blob)) === invoice.sha256;
        if (alive) setView({ url: (url = URL.createObjectURL(blob)), verified, type: blob.type });
      },
      (failure) => alive && setView({ url: "", verified: false, type: (failure as Error).message }),
    );
    return () => {
      alive = false;
      URL.revokeObjectURL(url);
    };
  }, [invoice.id, invoice.sha256]);
  if (!view.url) return <p className={view.type ? "status error" : "status"}>{view.type || "Loading the original…"}</p>;
  return (
    <figure className="original">
      {view.type.startsWith("image/") ? (
        <img src={view.url} alt={`Original of ${invoice.name}`} />
      ) : (
        <iframe src={view.url} title={`Original of ${invoice.name}`} />
      )}
      <figcaption>
        {view.verified && <ShieldCheck size={16} className="ok" aria-hidden />}
        {view.verified ? "SHA-256 verified: the original is unchanged" : "Original"}
      </figcaption>
    </figure>
  );
}

function ReviewForm({ invoice, user, onSaved }: { invoice: Invoice; user: User; onSaved: (next: Invoice) => void }) {
  const opened = useRef(Date.now());
  const planned = DEMO ? recorded("POST", `/api/invoices/${invoice.id}/review`)?.request : undefined;
  const fields = leaves({ ...invoice.data, irpf: invoice.data.irpf ?? { rate: null, amount: null } });
  const replayed = Object.fromEntries(leaves(planned?.data ?? {}));
  const [form, setForm] = useState(() =>
    Object.fromEntries(fields.map(([path, value]) => [path, text(path in replayed ? replayed[path] : value)])),
  );
  const [reason, setReason] = useState(planned?.reason ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const lead = user.roles.includes(LEAD);
  const blocked = invoice.findings.length > 0;
  const actions = [
    { action: "approve", label: "Approve", show: lead || !blocked, needs: lead && blocked },
    { action: "send_to_lead", label: "Send to lead", show: !lead, needs: false },
    { action: "reject", label: "Reject", show: lead, needs: true },
  ];
  async function decide(action: string) {
    const changed = fields.some(([path, value]) => text(value) !== form[path]);
    const body = { action, reason: reason.trim() || undefined, data: changed ? rebuild(invoice.data, form) : undefined };
    setSaving(true);
    try {
      onSaved(await api.review(invoice.id, { ...body, review_seconds: (Date.now() - opened.current) / 1000 }));
    } catch (failure) {
      setError((failure as Error).message);
    }
    setSaving(false);
  }
  const lines = fields.filter(([path]) => path.startsWith("line_items"));
  const low = (path: string) => (invoice.evidence?.[path]?.confidence ?? 1) < 0.8;
  const field = (path: string) => {
    const evidence = invoice.evidence?.[path];
    const note = evidence ? `${Math.round(evidence.confidence * 100)} %${evidence.page ? ` · page ${evidence.page}` : ""}` : "not read";
    return (
      <label key={path} className={low(path) ? "field low" : "field"}>
        <span>
          {words(path)} {low(path) && <TriangleAlert size={14} aria-label="low confidence" />}
        </span>
        <input value={form[path]} onChange={(event) => setForm({ ...form, [path]: event.target.value })} />
        <small>{note}</small>
      </label>
    );
  };
  return (
    <form className="fields" onSubmit={(event) => event.preventDefault()}>
      {fields.filter(([path]) => !path.startsWith("line_items")).map(([path]) => field(path))}
      {lines.length > 0 && (
        <details className="field wide" open={lines.some(([path]) => low(path))}>
          <summary>Line items ({lines.length} fields)</summary>
          <div className="fields">{lines.map(([path]) => field(path))}</div>
        </details>
      )}
      <label className="field wide">
        <span>Reason {lead ? "(required to reject or to approve with findings)" : "(optional)"}</span>
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {!lead && blocked && <p className="status">Invoices with findings or duplicates need the accounting lead.</p>}
      <div className="buttons">
        {actions
          .filter((item) => item.show)
          .map((item) => (
            <button
              key={item.action}
              type="button"
              className={item.action === "approve" ? "primary" : "secondary"}
              disabled={saving || (item.needs && !reason.trim()) || (DEMO && planned?.action !== item.action)}
              onClick={() => decide(item.action)}
            >
              {item.label}
            </button>
          ))}
      </div>
      {error && <p className="status error" role="alert">{error}</p>}
    </form>
  );
}

export function InvoiceCard({ id, user, onChange }: { id: string; user: User; onChange: () => void }) {
  const [invoice, setInvoice] = useState<Invoice>();
  const status = useRef<HTMLParagraphElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const next = await api.invoice(id);
        if (stopped) return;
        setInvoice(next);
        setError("");
        if (WORKING.includes(next.status)) setTimeout(poll, 2000);
        else onChange();
      } catch (failure) {
        if (stopped) return;
        setError((failure as Error).message);
        if (failure instanceof TypeError || ((failure as { status?: number }).status ?? 0) >= 500) setTimeout(poll, 10000);
      }
    };
    poll();
    return () => {
      stopped = true;
    };
  }, [id]);
  if (error && !invoice) return <p className="status error">{error}</p>;
  if (!invoice) return <p className="status"><LoaderCircle size={16} className="spin" aria-hidden /> Queued</p>;
  const steps = invoice.timeline ?? [];
  const start = Date.parse(steps[0]?.at ?? "");
  const seconds = (at: string) => ((Date.parse(at) - start) / 1000).toFixed(1);
  const number = invoice.data.invoice_number as string | null;
  const reviewed = steps.findLast((step) => step.name === "review_requested");
  return (
    <article className="card" aria-label={`Invoice ${number ?? invoice.name}`}>
      <h3>
        {number ?? invoice.name} <small>{(invoice.data.vendor_name as string) ?? ""}</small>
      </h3>
      <ul className="steps">
        {steps.map((step, index) => (
          <li key={index}>
            <CircleCheck size={14} className="ok" aria-hidden /> {words(step.name)} · {seconds(step.at)} s
          </li>
        ))}
        {WORKING.includes(invoice.status) && (
          <li>
            <LoaderCircle size={14} className="spin" aria-hidden /> Processing
          </li>
        )}
      </ul>
      <p className={invoice.status === "failed" ? "status error" : "status"} ref={status} tabIndex={-1}>
        {DONE[invoice.status]}
        {reviewed && invoice.status === "ready" && ` in ${seconds(reviewed.at)} s`}
      </p>
      {error && <p className="status error">{error}</p>}
      {invoice.findings.length > 0 && (
        <ul className="findings" aria-label="Findings">
          {invoice.findings.map((finding, index) => (
            <li key={index}>
              <CircleAlert size={14} className="bad" aria-hidden /> <strong>{words(finding.kind)}</strong> {finding.rule}
              {finding.duplicate_of && ` (invoice ${finding.duplicate_of})`}
              {Object.entries(finding.evidence ?? {}).map(([key, value]) => ` · ${words(key)}: ${value}`)}
            </li>
          ))}
        </ul>
      )}
      {(user.roles.includes(LEAD) ? REVIEWABLE : ["ready"]).includes(invoice.status) && (
        <div className="review">
          <Original invoice={invoice} />
          <ReviewForm invoice={invoice} user={user} onSaved={(next) => (setInvoice({ ...invoice, ...next }), onChange(), setTimeout(() => status.current?.focus()))} />
        </div>
      )}
      {!WORKING.includes(invoice.status) && (
        <details>
          <summary>Timeline</summary>
          <ol className="timeline">
            {steps.map((step, index) => (
              <li key={index}>
                <time dateTime={step.at}>{new Date(step.at).toLocaleString()}</time> {words(step.name)} by {step.by}
                {Object.entries(step.detail).map(([key, value]) => ` · ${words(key)}: ${key === "field" ? words(value) : value}`)}
              </li>
            ))}
          </ol>
          <p className="status">SHA-256 {invoice.sha256}</p>
        </details>
      )}
    </article>
  );
}
