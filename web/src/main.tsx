import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "./styles.css";
import { ArrowUp, Check, Copy, FileText, LoaderCircle, LogOut, Menu, MessageSquare, Paperclip } from "lucide-react";
import { Search, SquarePen, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Markdown from "react-markdown";
import { api, DEMO, LEAD, replay, RUNS, type Batch, type Conversation, type Invoice, type Run, type User } from "./api";
import { InvoiceCard } from "./Invoice";

const BRAND = `${import.meta.env.BASE_URL}brand/`;
const SUGGESTIONS = [
  { text: "Upload this month's invoices", kind: "upload" },
  { text: "Which invoices are waiting for approval?", kind: "ask" },
  { text: "Show probable duplicates", kind: "ask" },
  { text: "Export approved invoices", kind: "export" },
];
type Entry =
  | { kind: "user"; text: string; files?: string[] }
  | { kind: "answer"; text: string; about?: string }
  | { kind: "invoices"; ids: string[] }
  | { kind: "export"; batch: Batch }
  | { kind: "error"; text: string };
type Item = { key: string; label: string; go: () => void; icon: typeof FileText };

function Answer({ text, at }: { text: string; at: number }) {
  const cited: string[] = [];
  const body = text.replace(/\[INV-([^\]\s]+)\]/g, (_, number: string) => {
    const index = (cited.includes(number) ? cited.indexOf(number) : cited.push(number) - 1) + 1;
    return `[${index}](#source-${at}-${index})`;
  });
  return (
    <>
      <div className="answer">
        <Markdown disallowedElements={["img"]} urlTransform={(url) => (url.startsWith("#") ? url : null)}>
          {body}
        </Markdown>
      </div>
      {cited.length > 0 && (
        <ol className="sources" aria-label="Sources">
          {cited.map((number, index) => (
            <li key={number} id={`source-${at}-${index + 1}`}>
              Invoice {number}
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

function Actions({ text, about }: { text?: string; about: string }) {
  const [vote, setVote] = useState<boolean>();
  const [copied, setCopied] = useState(false);
  const rate = (helpful: boolean) => (setVote(helpful), api.feedback(helpful, about.slice(0, 64)).catch(() => undefined));
  return (
    <div className="actions">
      {text && (
        <button className="icon" aria-label={copied ? "Copied" : "Copy"} onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}>
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      )}
      <button className="icon" aria-label="Helpful" aria-pressed={vote === true} onClick={() => rate(true)}>
        <ThumbsUp size={16} />
      </button>
      <button className="icon" aria-label="Not helpful" aria-pressed={vote === false} onClick={() => rate(false)}>
        <ThumbsDown size={16} />
      </button>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User>({ name: DEMO ? "Visitor" : "", roles: [] });
  const [entries, setEntries] = useState<Entry[]>([]);
  const [conversation, setConversation] = useState<string>();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [queue, setQueue] = useState<Invoice[]>([]);
  const [active, setActive] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [filter, setFilter] = useState<string>();
  const [menu, setMenu] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const thread = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const timer = useRef(0);
  const lead = user.roles.includes(LEAD);
  const fail = (failure: unknown) => setEntries((list) => [...list, { kind: "error", text: (failure as Error).message }]);

  function refresh(talks = true) {
    if (DEMO || !user.roles.length) return;
    Promise.all((lead ? ["ready", "with_lead"] : ["ready"]).map(api.queue)).then((lists) => setQueue(lists.flat()), fail);
    if (talks) api.conversations().then(setConversations, fail);
  }
  const later = () => (clearTimeout(timer.current), (timer.current = window.setTimeout(refresh, 1000, false)));
  useEffect(() => {
    if (!DEMO) api.me().then((me) => (setUser(me), me.roles.length || fail(new Error("Your account has no Folium role."))), fail);
  }, []);
  useEffect(refresh, [user]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
    if (document.activeElement === document.body) thread.current?.focus({ preventScroll: true });
  }, [entries.length]);

  async function guard(text: string, work: (put: (entry?: Entry) => boolean) => Promise<unknown>, files?: string[]) {
    const mine = generation.current;
    const put = (entry?: Entry) => mine === generation.current && (!entry || (setEntries((list) => [...list, entry]), true));
    setBusy(true);
    put({ kind: "user", text, files });
    await work(put).catch((failure) => put({ kind: "error", text: (failure as Error).message }));
    if (put()) setBusy(false);
  }
  const upload = (files: File[], text = `Upload ${files.length} invoice${files.length > 1 ? "s" : ""}`) =>
    guard(text, async (put) => put({ kind: "invoices", ids: (await api.upload(files)).map((item) => item.id) }), files.map((file) => file.name));
  const open = (id: string, text: string) => guard(text, async (put) => put({ kind: "invoices", ids: [id] }));
  const exportBatch = (text = "Export approved invoices") =>
    guard(text, async (put) => {
      const key = crypto.randomUUID();
      const batch = await api.exportBatch(key).catch((failure) => (failure instanceof TypeError ? api.exportBatch(key) : Promise.reject(failure)));
      put({ kind: "export", batch });
      refresh();
    });
  const ask = (text: string) =>
    guard(text, async (put) => {
      const response = await api.chat(text, conversation);
      const about = response.headers.get("X-Conversation") ?? undefined;
      const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
      let shown: Entry = { kind: "answer", text: "", about };
      if (put(shown)) setConversation(about);
      for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
        if (!put()) return reader.cancel();
        const before: Entry = shown;
        const next: Entry = { kind: "answer", text: (before as { text: string }).text + chunk.value, about };
        shown = next;
        setEntries((list) => list.map((entry) => (entry === before ? next : entry)));
      }
      refresh();
    });

  function reset(key = "", next: Entry[] = []) {
    generation.current += 1;
    setBusy(false);
    setEntries(next);
    setActive(key);
    setMenu(false);
    setConversation(undefined);
  }
  function play(run: Run) {
    reset(run.title);
    replay(run);
    setUser(run.user);
    const start = {
      upload: () => upload((run.files ?? []).map((name) => new File([], name)), run.prompt),
      ask: () => ask(run.prompt),
      export: () => exportBatch(run.prompt),
      open: () => open(run.invoice ?? "", run.prompt),
    };
    start[run.kind]();
  }
  function suggest(text: string, kind: string) {
    const run = RUNS.find((item) => item.prompt === text);
    if (DEMO) return run && play(run);
    if (kind === "upload") return picker.current?.click();
    return kind === "export" ? exportBatch() : ask(text);
  }
  function send() {
    if (!draft.trim() || busy || DEMO) return;
    ask(draft.trim());
    setDraft("");
  }

  const sections: [string, Item[]][] = DEMO
    ? [["Recorded runs", RUNS.map((run) => ({ key: run.title, label: run.title, go: () => play(run), icon: FileText }))]]
    : [
        [
          "Waiting for review",
          queue.map((item) => {
            const label = String(item.data.invoice_number ?? item.name);
            return { key: item.id, label, go: () => (reset(item.id), open(item.id, `Review ${label}`)), icon: FileText };
          }),
        ],
        [
          "Conversations",
          conversations.map((item) => {
            const turns = item.turns.map((turn): Entry => (turn.role === "user" ? { kind: "user", text: turn.text } : { kind: "answer", text: turn.text, about: item.id }));
            return { key: item.id, label: item.title || "Untitled conversation", go: () => (reset(item.id, turns), setConversation(item.id)), icon: MessageSquare };
          }),
        ],
      ];
  const initial = (user.name || "?").charAt(0).toUpperCase();

  return (
    <div className="app">
      {DEMO && <header className="band">Demo mode · recorded runs from the deployed system</header>}
      <div className="layout">
        <button className="icon menu" aria-label="Sidebar" aria-expanded={menu} onClick={() => setMenu(!menu)}>
          <Menu size={20} />
        </button>
        <aside className={menu ? "sidebar open" : "sidebar"} aria-label="Sidebar">
          <h1>
            <img src={`${BRAND}folium-logo.svg`} alt="Folium" height={28} />
          </h1>
          <div className="row">
            <button className="primary" onClick={() => reset()}>
              <SquarePen size={16} aria-hidden /> New chat
            </button>
            <button className="icon round" aria-label="Search" aria-expanded={filter !== undefined} onClick={() => setFilter(filter === undefined ? "" : undefined)}>
              <Search size={16} />
            </button>
          </div>
          {filter !== undefined && <input className="search" aria-label="Search the list" autoFocus value={filter} onChange={(event) => setFilter(event.target.value)} />}
          <nav aria-label={DEMO ? "Recorded runs" : "Invoices and conversations"}>
            {sections.map(([heading, items]) => (
              <section key={heading}>
                <h2>{heading}</h2>
                <ul>
                  {items
                    .filter((item) => item.label.toLowerCase().includes((filter ?? "").toLowerCase()))
                    .map(({ key, label, go, icon: Icon }) => (
                      <li key={key}>
                        <button className={key === active ? "item selected" : "item"} aria-current={key === active} onClick={go}>
                          <Icon size={16} aria-hidden /> <span>{label}</span>
                        </button>
                      </li>
                    ))}
                </ul>
                {items.length === 0 && <p className="status">{DEMO ? "No recorded runs yet." : "Nothing here yet."}</p>}
              </section>
            ))}
          </nav>
          <div className="me">
            <span className="avatar" aria-hidden>
              {initial}
            </span>
            <span>
              {user.name || "Signed out"}
              <small>{lead ? "Accounting lead" : user.roles.length ? "Clerk" : DEMO ? "Demo" : "No Folium role"}</small>
            </span>
            {!DEMO && (
              <a className="icon" href="/.auth/logout" aria-label="Sign out">
                <LogOut size={16} />
              </a>
            )}
          </div>
        </aside>
        <main>
          {entries.length === 0 ? (
            <div className="empty">
              <img src={`${BRAND}folium-icon.svg`} alt="" width={56} height={56} />
              <h2>Supplier invoices read, checked and de-duplicated, ready for your review.</h2>
              <div className="suggestions">
                {SUGGESTIONS.map(({ text, kind }) => (
                  <button key={text} className="suggestion" disabled={busy || (DEMO ? !RUNS.some((run) => run.prompt === text) : kind === "export" && !lead)} onClick={() => suggest(text, kind)}>
                    {text}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="thread" role="log" aria-label="Conversation" key={generation.current} ref={thread} tabIndex={-1}>
              {entries.map((entry, index) =>
                entry.kind === "user" ? (
                  <div className="turn user" key={index}>
                    <span className="avatar" aria-hidden>
                      {initial}
                    </span>
                    <p>
                      {entry.text}
                      {entry.files && <small> {entry.files.join(", ")}</small>}
                    </p>
                  </div>
                ) : (
                  <section className="turn product" key={index} aria-label="Folium" aria-busy={entry.kind === "answer" && busy && index === entries.length - 1}>
                    <p className="name">Folium</p>
                    {entry.kind === "error" && <p className="status error" role="alert">{entry.text}</p>}
                    {entry.kind === "answer" && (entry.text ? <Answer text={entry.text} at={index} /> : <p className="status"><LoaderCircle size={16} className="spin" aria-hidden /> Thinking</p>)}
                    {entry.kind === "invoices" && entry.ids.map((id) => <InvoiceCard key={id} id={id} user={user} onChange={later} />)}
                    {entry.kind === "export" && (
                      <p>
                        Batch {entry.batch.id} exported {entry.batch.invoices.length} approved invoices, once.
                        {!DEMO && <> Download the <a href={`/api/exports/${entry.batch.id}?format=csv`}>CSV</a> or the <a href={`/api/exports/${entry.batch.id}?format=json`}>JSON</a>.</>}
                      </p>
                    )}
                    {entry.kind !== "error" && <Actions text={entry.kind === "answer" ? entry.text : undefined} about={entry.kind === "answer" ? (entry.about ?? "answer") : entry.kind === "export" ? entry.batch.id : entry.ids.join(",")} />}
                  </section>
                ),
              )}
              <div ref={end} />
            </div>
          )}
          <form className="composer" onSubmit={(event) => (event.preventDefault(), send())}>
            <input
              ref={picker}
              type="file"
              multiple
              hidden
              accept="application/pdf,image/jpeg,image/png"
              onChange={(event) => {
                const files = [...(event.target.files ?? [])];
                event.target.value = "";
                if (files.length) upload(files);
              }}
            />
            <button type="button" className="icon round" aria-label="Attach invoices" disabled={DEMO || busy} onClick={() => picker.current?.click()}>
              <Paperclip size={18} />
            </button>
            <textarea
              aria-label="Message"
              rows={1}
              value={draft}
              disabled={DEMO}
              placeholder={DEMO ? "Free text needs the deployed system: pick a recorded run" : "Ask about your invoices, or attach a batch"}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && (event.preventDefault(), send())}
            />
            <button type="submit" className="send" aria-label="Send" disabled={DEMO || busy || !draft.trim()}>
              <ArrowUp size={18} />
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
