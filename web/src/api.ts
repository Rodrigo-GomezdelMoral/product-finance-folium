export type Evidence = { confidence: number; page: number | null };
export type Finding = { kind: string; rule?: string; evidence?: Record<string, string>; duplicate_of?: string | null };
export type Step = { name: string; at: string; by: string; detail: Record<string, string> };
export type Invoice = {
  id: string;
  sha256: string;
  status: string;
  name: string;
  media_type?: string;
  data: Record<string, unknown>;
  evidence?: Record<string, Evidence>;
  findings: Finding[];
  timeline?: Step[];
};
export type User = { name: string; roles: string[] };
export type Turn = { role: string; text: string };
export type Conversation = { id: string; title: string; turns: Turn[] };
export type Batch = { id: string; created_at: string; invoices: string[] };
export type Review = { action: string; reason?: string; data?: Record<string, unknown>; review_seconds?: number };
export type Exchange = {
  method: string;
  path: string;
  status: number;
  ms: number;
  request?: Review;
  json?: unknown;
  text?: string;
  base64?: string;
  type?: string;
  headers?: Record<string, string>;
};
export type Run = {
  title: string;
  prompt: string;
  kind: "upload" | "ask" | "export" | "open";
  files?: string[];
  invoice?: string;
  user: User;
  recorded: string;
  exchanges: Exchange[];
};

export const DEMO = import.meta.env.VITE_DEMO_MODE === "true";
const recordings = DEMO ? Object.values(import.meta.glob<Run | Run[]>("./demo/runs/*.json", { eager: true, import: "default" })) : [];
export const RUNS = recordings.flat();
export const LEAD = "Invoice.Approve";

let replaying: Exchange[] = [];
const used = new Set<Exchange>();

export function replay(run: Run) {
  replaying = run.exchanges;
  used.clear();
}

export function recorded(method: string, path: string): Exchange | undefined {
  const same = replaying.filter((item) => item.method === method && item.path === path);
  return same.find((item) => !used.has(item)) ?? same.at(-1);
}

function respond(item: Exchange): Response {
  const bytes = item.base64 && Uint8Array.from(atob(item.base64), (char) => char.charCodeAt(0));
  const body = bytes || (item.json === undefined ? (item.text ?? null) : JSON.stringify(item.json));
  return new Response(body, { status: item.status, headers: { "content-type": item.type ?? "application/json", ...item.headers } });
}

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  if (!DEMO) return fetch(path, init);
  const item = recorded(init.method ?? "GET", path);
  if (!item) return Response.json({ detail: "This step is not part of the recording." }, { status: 404 });
  used.add(item);
  await new Promise((done) => setTimeout(done, item.ms));
  return respond(item);
}

async function checked(path: string, init?: RequestInit): Promise<Response> {
  const response = await call(path, init);
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : `the request failed with status ${response.status}`;
  throw Object.assign(new Error(`${detail.charAt(0).toUpperCase()}${detail.slice(1)}.`), { status: response.status });
}

const json = async <T>(path: string, init?: RequestInit): Promise<T> => (await checked(path, init)).json();
const post = (body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json", ...headers },
  body: JSON.stringify(body),
});

export const api = {
  me: () => json<User>("/api/me"),
  queue: (status: string) => json<Invoice[]>(`/api/invoices?status=${status}`),
  invoice: (id: string) => json<Invoice>(`/api/invoices/${id}`),
  original: async (id: string) => (await checked(`/api/invoices/${id}/original`)).blob(),
  review: (id: string, body: Review) => json<Invoice>(`/api/invoices/${id}/review`, post(body)),
  conversations: () => json<Conversation[]>("/api/conversations"),
  chat: (message: string, conversation?: string) => checked("/api/chat", post({ message, conversation })),
  feedback: (helpful: boolean, about: string) => call("/api/feedback", post({ helpful, about })),
  exportBatch: (key: string) => json<Batch>("/api/exports", { method: "POST", headers: { "Idempotency-Key": key } }),
  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return json<Invoice[]>("/api/invoices", { method: "POST", body: form });
  },
};
