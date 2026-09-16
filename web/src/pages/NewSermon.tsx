import { useMemo, useState } from "react";
import {
  Button,
  Chip,
  ConfirmDialog,
  Field,
  PageHeader,
  SectionCard,
  Toast,
  Toggle,
  inputCls,
} from "../components/ui";

type UploadTab = "browser" | "server";
type ApprovalMode = "manual" | "auto_render" | "auto_upload";

const speakers = ["Speaker A", "Speaker B", "Speaker C"];
const eventTypes = ["Sunday Service", "Midweek Gathering", "Conference", "Funeral", "Wedding", "Other"];
const supportedFormats = ["MP3", "WAV", "M4A", "MP4", "MOV"];
const endingCards = [
  { id: "card-a", label: "Card A", sub: "Dark title card" },
  { id: "card-b", label: "Card B", sub: "Light title card" },
  { id: "card-c", label: "Card C", sub: "Verse card" },
];

const initialMeta = { title: "", speaker: "", date: "", series: "", eventType: "", scripture: "" };

export function NewSermon() {
  const [uploadTab, setUploadTab] = useState<UploadTab>("browser");
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [serverPath, setServerPath] = useState("");
  const [meta, setMeta] = useState(initialMeta);
  const [enhance, setEnhance] = useState(true);
  const [transcribe, setTranscribe] = useState(true);
  const [aiMeta, setAiMeta] = useState(true);
  const [approval, setApproval] = useState<ApprovalMode>("manual");
  const [endingCard, setEndingCard] = useState<string>("none");
  const [fadeBlack, setFadeBlack] = useState(true);
  const [confirmReset, setConfirmReset] = useState(false);
  const [starting, setStarting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const set = (k: keyof typeof initialMeta) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setMeta((m) => ({ ...m, [k]: e.target.value }));

  const serverValid = serverPath.trim().startsWith("/") && serverPath.trim().length > 3;
  const hasSource = uploadTab === "browser" ? fileName !== null : serverValid;

  const missing = useMemo(() => {
    const list: string[] = [];
    if (!hasSource) list.push(uploadTab === "browser" ? "source file" : "valid server path");
    if (!meta.title.trim()) list.push("title");
    if (!meta.speaker) list.push("speaker");
    if (!meta.date) list.push("date");
    return list;
  }, [hasSource, uploadTab, meta.title, meta.speaker, meta.date]);

  const valid = missing.length === 0;
  const helper = valid ? "Ready to queue. This mock run appears under Jobs." : `Missing: ${missing.join(", ")}.`;

  const pickMockFile = () => setFileName("sample-sermon-upload.mp3");

  const resetAll = () => {
    setFileName(null);
    setServerPath("");
    setMeta(initialMeta);
    setEnhance(true);
    setTranscribe(true);
    setAiMeta(true);
    setApproval("manual");
    setEndingCard("none");
    setFadeBlack(true);
  };

  const start = () => {
    if (!valid || starting) return;
    setStarting(true);
    window.setTimeout(() => {
      setStarting(false);
      setToast("Processing queued (mock). Track it under Jobs.");
      window.setTimeout(() => setToast(null), 3000);
    }, 1200);
  };

  const onTabsKey = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    setUploadTab((t) => {
      if (e.key === "ArrowRight") return t === "browser" ? "server" : "browser";
      return t === "server" ? "browser" : "server";
    });
  };

  const summaryBits = [
    uploadTab === "browser" ? fileName ?? "no file" : serverValid ? serverPath.trim() : "no path",
    meta.title.trim() || "untitled",
    meta.speaker || "no speaker",
    meta.date || "no date",
    enhance ? "enhance" : "no enhance",
    transcribe ? "transcribe" : "no transcribe",
    aiMeta ? "ai meta" : "no ai meta",
  ];

  return (
    <div className="flex flex-col gap-4 pb-32">
      <PageHeader
        title="New Sermon"
        sub="Upload, describe, then queue the pipeline. Mock only, nothing is sent."
        actions={
          <Button variant="ghost" onClick={() => setConfirmReset(true)}>
            Reset
          </Button>
        }
      />

      <SectionCard n={1} title="Upload" sub="Pick one source. Browser upload or a path already on the server.">
        <div
          role="tablist"
          aria-label="Upload source"
          onKeyDown={onTabsKey}
          className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-ink p-1"
        >
          {(
            [
              { id: "browser", label: "Browser Upload" },
              { id: "server", label: "Server Path" },
            ] as { id: UploadTab; label: string }[]
          ).map((t) => {
            const selected = uploadTab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setUploadTab(t.id)}
                className={`flex min-h-[44px] flex-1 items-center justify-center whitespace-nowrap rounded-md px-3 text-sm font-semibold transition-colors ${
                  selected ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {uploadTab === "browser" ? (
          <div className="mt-3">
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop a sermon file here, or press Enter to pick a mock file"
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                pickMockFile();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  pickMockFile();
                }
              }}
              className={`flex min-h-[10rem] flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
                dragOver ? "border-accent bg-raised" : "border-line bg-ink"
              }`}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-8 w-8 text-muted" aria-hidden="true">
                <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p className="text-sm font-semibold">
                {fileName ?? "Drag a file here or choose one"}
              </p>
              <p className="text-xs text-muted">Files stay local in this mock. Nothing is uploaded.</p>
              <Button variant="primary" onClick={pickMockFile}>
                {fileName ? "Replace file" : "Choose file"}
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Supported formats">
              {supportedFormats.map((f) => (
                <Chip key={f} tone="neutral">
                  {f}
                </Chip>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">
              Large files (over ~500 MB) may take a while on slow connections. Prefer Server Path for those.
            </p>
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            <Field label="Server path" htmlFor="server-path" hint="Absolute path on the processing machine, e.g. /media/sample-sermon.mp3">
              <input
                id="server-path"
                value={serverPath}
                onChange={(e) => setServerPath(e.target.value)}
                placeholder="/media/sample-sermon.mp3"
                inputMode="text"
                autoComplete="off"
                className={inputCls}
              />
            </Field>
            <div className="flex flex-wrap gap-2" aria-live="polite" aria-label="Path validation">
              <Chip tone={serverValid ? "ok" : "neutral"}>{serverValid ? "exists" : "no check yet"}</Chip>
              <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "42.1 MB" : "size —"}</Chip>
              <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "mp3 · audio" : "type —"}</Chip>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard n={2} title="Metadata" sub="Title, speaker, and date are required. The rest sharpens search and display.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Title (required)" htmlFor="ns-title">
            <input id="ns-title" value={meta.title} onChange={set("title")} placeholder="Sample teaching title" className={inputCls} />
          </Field>
          <Field label="Speaker (required)" htmlFor="ns-speaker">
            <select id="ns-speaker" value={meta.speaker} onChange={set("speaker")} className={inputCls}>
              <option value="">Choose a speaker…</option>
              {speakers.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date (required)" htmlFor="ns-date">
            <input id="ns-date" type="date" value={meta.date} onChange={set("date")} className={inputCls} />
          </Field>
          <Field label="Series" htmlFor="ns-series">
            <input id="ns-series" value={meta.series} onChange={set("series")} placeholder="Sample Series A" className={inputCls} />
          </Field>
          <Field label="Event type" htmlFor="ns-event">
            <select id="ns-event" value={meta.eventType} onChange={set("eventType")} className={inputCls}>
              <option value="">Choose an event type…</option>
              {eventTypes.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Scripture" htmlFor="ns-scripture" hint="Free text, e.g. Psalm 23">
            <input id="ns-scripture" value={meta.scripture} onChange={set("scripture")} placeholder="Psalm 23" className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard n={3} title="Processing options" sub="Toggle pipeline stages and the edit approval path.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Toggle checked={enhance} onChange={setEnhance} label="Enhance audio" hint="Noise cleanup before transcription." />
          <Toggle checked={transcribe} onChange={setTranscribe} label="Transcribe" hint="Speech-to-text for captions and search." />
          <Toggle checked={aiMeta} onChange={setAiMeta} label="AI metadata" hint="Draft title, summary, and tags." />
        </div>

        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Edit approval mode</legend>
          <div className="mt-2 grid grid-cols-1 gap-2">
            {(
              [
                { id: "manual", label: "Manual review", sub: "Nothing renders until the plan is approved." },
                { id: "auto_render", label: "Auto render", sub: "Renders locally, waits before any upload." },
                { id: "auto_upload", label: "Auto upload", sub: "Renders and pushes without a review stop." },
              ] as { id: ApprovalMode; label: string; sub: string }[]
            ).map((o) => (
              <label key={o.id} className="flex min-h-[44px] cursor-pointer items-start gap-2 rounded-md border border-line p-3">
                <input
                  type="radio"
                  name="approval-mode"
                  value={o.id}
                  checked={approval === o.id}
                  onChange={() => setApproval(o.id)}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-semibold">{o.label}.</span> <span className="text-muted">{o.sub}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Ending card image</legend>
          <p className="mt-1 text-xs text-muted">
            Fade to black plays under the ending card; with no card it simply fades the picture itself.
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Ending card">
            <button
              type="button"
              role="radio"
              aria-checked={endingCard === "none"}
              onClick={() => setEndingCard("none")}
              className={`flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border p-3 text-sm transition-colors ${
                endingCard === "none" ? "border-accent bg-raised" : "border-line bg-ink hover:border-muted"
              }`}
            >
              <span className="font-semibold">No card</span>
              <span className="text-xs text-muted">fade only</span>
            </button>
            {endingCards.map((c) => {
              const selected = endingCard === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  aria-label={`${c.label}, ${c.sub}`}
                  onClick={() => setEndingCard(c.id)}
                  className={`flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border p-3 transition-colors ${
                    selected ? "border-accent bg-raised" : "border-line bg-ink hover:border-muted"
                  }`}
                >
                  <span aria-hidden="true" className="flex h-10 w-16 items-center justify-center rounded bg-raised font-mono text-xs text-muted">
                    {c.label}
                  </span>
                  <span className="text-xs text-muted">{c.sub}</span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="mt-3">
          <Toggle checked={fadeBlack} onChange={setFadeBlack} label="Fade to black" hint="Short fade into the ending hold." />
        </div>
      </SectionCard>

      <div className="flex flex-col gap-2">
        <Button variant="primary" onClick={start} disabled={!valid || starting} aria-busy={starting} className="w-full sm:w-auto sm:self-start">
          {starting ? "Queueing…" : "Start Processing"}
        </Button>
        <p className="text-xs text-muted" role="status" aria-live="polite">
          {helper}
        </p>
      </div>

      <div
        aria-label="Selection summary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-ink/95 backdrop-blur"
      >
        <div className="mx-auto max-w-shell overflow-x-auto px-4 py-2">
          <p className="truncate font-mono text-xs text-muted" aria-live="polite" title={summaryBits.join(" · ")}>
            {summaryBits.join(" · ")}
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="Reset this form?"
        body="Every field on this page returns to its default. This cannot be undone."
        confirmLabel="Reset form"
        onClose={() => setConfirmReset(false)}
        onConfirm={resetAll}
      />
      <Toast message={toast} />
    </div>
  );
}
