import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
import {
  brandingApi,
  cloudApi,
  isLive,
  outputDirApi,
  serverPathApi,
  uploadApi,
  type ApiCloudFile,
  type ApiCloudRemote,
  type BrandingItem,
  type ServerPathStat,
} from "../api/client";
import { CloudBrowser, MOCK_REMOTES } from "../components/CloudBrowser";
import { FileExplorerDialog } from "../components/FileExplorer";

type UploadTab = "browser" | "server";
type AutoEditMode = "interactive" | "auto";

function CloudFileDialog({
  open,
  name,
  provider,
  attachedDriveId,
  onClose,
  onUse,
}: {
  open: boolean;
  name: string;
  provider?: string;
  attachedDriveId?: string;
  onClose: () => void;
  onUse: (item: ApiCloudFile) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [path, setPath] = useState("");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  useEffect(() => {
    if (open) setPath("");
  }, [open, name]);
  return (
    <dialog
      ref={ref}
      aria-label={`Browse ${name}`}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="w-[min(44rem,calc(100vw-2rem))] max-h-[85vh] overflow-y-auto rounded-xl border border-line bg-surface p-4 text-mist backdrop:bg-black/60"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Pick a cloud file</h2>
        <Button onClick={onClose}>Close</Button>
      </div>
      <CloudBrowser
        name={name}
        path={path}
        onPath={setPath}
        onUse={onUse}
        provider={provider}
        attachedDriveId={attachedDriveId}
      />
    </dialog>
  );
}

// Static full SermonAudio eventType enum (mirrors ui.sermon_metadata.DEFAULT_EVENT_TYPES).
const eventTypes = [
  "Audiobook",
  "Bible Study",
  "Camp Meeting",
  "Chapel Service",
  "Children",
  "Classic Audio",
  "Conference",
  "Current Events",
  "Debate",
  "Devotional",
  "Funeral Service",
  "Midweek Service",
  "Miscellaneous",
  "Open-Air Ministry",
  "Podcast",
  "Prayer Meeting",
  "Question & Answer",
  "Radio Broadcast",
  "Sermon Clip",
  "Special Meeting",
  "Sunday - AM",
  "Sunday - PM",
  "Sunday School",
  "Sunday Service",
  "Teaching",
  "Testimony",
  "TV Broadcast",
  "Wedding",
  "Youth",
];
const supportedFormats = ["MP3", "WAV", "M4A", "MP4", "MOV"];

const initialMeta = { title: "", speaker: "", date: "", series: "", eventType: "", scripture: "" };

export function NewSermon() {
  const [searchParams] = useSearchParams();
  const prefilledPath = searchParams.get("server_path") ?? "";
  const [uploadTab, setUploadTab] = useState<UploadTab>(prefilledPath ? "server" : "browser");
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [serverPath, setServerPath] = useState(prefilledPath);
  const [pathStat, setPathStat] = useState<ServerPathStat | null>(null);
  const [statPending, setStatPending] = useState(false);
  const [meta, setMeta] = useState(initialMeta);
  const [enhance, setEnhance] = useState(true);
  const [transcribe, setTranscribe] = useState(true);
  const [aiMeta, setAiMeta] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [autoEdit, setAutoEdit] = useState(false);
  const [autoEditMode, setAutoEditMode] = useState<AutoEditMode>("interactive");
  const [logoPath, setLogoPath] = useState<string>("none");
  const [brandingFiles, setBrandingFiles] = useState<BrandingItem[]>([]);
  const [uploadingCard, setUploadingCard] = useState(false);
  const [fadeBlack, setFadeBlack] = useState(true);
  const [confirmReset, setConfirmReset] = useState(false);
  const [starting, setStarting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [fileObj, setFileObj] = useState<File | null>(null);
  const [queuedJob, setQueuedJob] = useState<string | null>(null);
  const [cloudRemotes, setCloudRemotes] = useState<ApiCloudRemote[]>([]);
  const [cloudPick, setCloudPick] = useState("");
  const [cloudOpen, setCloudOpen] = useState(false);
  const [localOpen, setLocalOpen] = useState(false);
  const [outputDir, setOutputDir] = useState("processed_sermons");
  const [outputSource, setOutputSource] = useState<"user" | "default">("default");
  const [outputOpen, setOutputOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const cardInput = useRef<HTMLInputElement>(null);

  const set = (k: keyof typeof initialMeta) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setMeta((m) => ({ ...m, [k]: e.target.value }));

  // Live server-path stat: debounce the input, then ask the server to stat() it.
  useEffect(() => {
    if (!isLive || uploadTab !== "server") return;
    const trimmed = serverPath.trim();
    if (!trimmed.startsWith("/") || trimmed.length <= 3) {
      setPathStat(null);
      return;
    }
    setStatPending(true);
    const timer = window.setTimeout(() => {
      void serverPathApi
        .stat(trimmed)
        .then((info) => setPathStat(info))
        .catch(() => setPathStat(null))
        .finally(() => setStatPending(false));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [serverPath, uploadTab]);

  // Live ending-card options: the user's own branding uploads.
  useEffect(() => {
    if (!isLive) return;
    void brandingApi
      .list()
      .then((r) => setBrandingFiles(r.items))
      .catch(() => setBrandingFiles([]));
  }, []);

  // Cloud remotes for the "From cloud" picker.
  useEffect(() => {
    if (!isLive) {
      setCloudRemotes(MOCK_REMOTES);
      return;
    }
    void cloudApi
      .list()
      .then((r) => setCloudRemotes(r.items))
      .catch(() => setCloudRemotes([]));
  }, []);

  // Resolved per-user output location (default for the next sermon).
  useEffect(() => {
    if (!isLive) return;
    void outputDirApi
      .get()
      .then((r) => {
        setOutputDir(r.output_dir);
        setOutputSource(r.source);
      })
      .catch(() => undefined);
  }, []);

  const useCloudFile = (item: ApiCloudFile) => {
    setServerPath(`remote:${cloudPick}:${item.path}`);
    setCloudOpen(false);
  };

  const useLocalFile = (path: string) => {
    setServerPath(path);
    setLocalOpen(false);
  };

  const pickOutputDir = (path: string) => {
    setOutputOpen(false);
    setOutputDir(path);
    setOutputSource("user");
    if (!isLive) {
      showToast("Output location updated (mock).");
      return;
    }
    void outputDirApi
      .put(path)
      .then((r) => {
        setOutputDir(r.output_dir);
        showToast("Output location saved as your default.");
      })
      .catch((e) => showToast(`Could not save output location: ${(e as Error).message}`));
  };

  const remotePath = /^remote:[A-Za-z0-9._-]{1,64}:.+$/.test(serverPath.trim());
  const pathLooksValid =
    (serverPath.trim().startsWith("/") && serverPath.trim().length > 3) || remotePath;
  const serverValid = isLive
    ? remotePath || (pathStat ? pathStat.exists && pathStat.is_file !== false : pathLooksValid)
    : pathLooksValid;
  const browserHasSource = isLive ? fileObj !== null : fileName !== null;
  const hasSource = uploadTab === "browser" ? browserHasSource : serverValid;

  const missing = useMemo(() => {
    const list: string[] = [];
    if (!hasSource) list.push(uploadTab === "browser" ? "source file" : "valid server path");
    if (!meta.title.trim()) list.push("title");
    if (!meta.speaker.trim()) list.push("speaker");
    if (!meta.date) list.push("date");
    return list;
  }, [hasSource, uploadTab, meta.title, meta.speaker, meta.date]);

  const valid = missing.length === 0;
  const helper = valid
    ? isLive
      ? "Ready to queue. The pipeline run appears under Jobs."
      : "Ready to queue. This mock run appears under Jobs."
    : `Missing: ${missing.join(", ")}.`;

  const pickMockFile = () => setFileName("sample-sermon-upload.mp3");

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 4000);
  };

  const resetAll = () => {
    setFileName(null);
    setFileObj(null);
    setQueuedJob(null);
    setServerPath("");
    setPathStat(null);
    setMeta(initialMeta);
    setEnhance(true);
    setTranscribe(true);
    setAiMeta(true);
    setDryRun(false);
    setAutoEdit(false);
    setAutoEditMode("interactive");
    setLogoPath("none");
    setFadeBlack(true);
  };

  const clearFormKeepJob = (jobId: string) => {
    setFileName(null);
    setFileObj(null);
    setQueuedJob(jobId);
    setServerPath("");
    setPathStat(null);
    setMeta(initialMeta);
    setEnhance(true);
    setTranscribe(true);
    setAiMeta(true);
    setDryRun(false);
    setAutoEdit(false);
    setAutoEditMode("interactive");
    setLogoPath("none");
    setFadeBlack(true);
  };

  const commonPayload = () => ({
    title: meta.title.trim(),
    speaker: meta.speaker.trim(),
    recorded_date: meta.date,
    event_type: meta.eventType || "Sunday Service",
    series_title: meta.series.trim(),
    bible_text: meta.scripture.trim(),
    scripture: meta.scripture.trim(),
    skip_audio: !enhance,
    skip_transcription: !transcribe,
    skip_ai_generation: !aiMeta,
    dry_run: dryRun,
    auto_edit_enabled: autoEdit,
    auto_edit_mode: autoEdit ? autoEditMode : null,
    logo_path: logoPath === "none" ? "" : logoPath,
    fade_to_black: fadeBlack,
    output_dir: outputDir,
  });

  const start = () => {
    if (!valid || starting) return;
    if (!isLive) {
      setStarting(true);
      window.setTimeout(() => {
        setStarting(false);
        setToast("Processing queued (mock). Track it under Jobs.");
        window.setTimeout(() => setToast(null), 3000);
      }, 1200);
      return;
    }
    setStarting(true);
    if (uploadTab === "browser" && fileObj) {
      const form = new FormData();
      form.append("file", fileObj);
      const payload = commonPayload();
      for (const [k, v] of Object.entries(payload)) {
        if (v === null || v === undefined) continue;
        form.append(k, typeof v === "boolean" ? String(v) : String(v));
      }
      void uploadApi
        .upload(form)
        .then((r) => {
          setStarting(false);
          clearFormKeepJob(r.job_id);
          showToast(`Upload queued as job ${r.job_id}.`);
        })
        .catch((e) => {
          setStarting(false);
          showToast(`Could not queue: ${(e as Error).message}`);
        });
      return;
    }
    void serverPathApi
      .create({ container_path: serverPath.trim(), ...commonPayload() })
      .then((r) => {
        setStarting(false);
        clearFormKeepJob(r.job_id);
        showToast(`Server file queued as job ${r.job_id}.`);
      })
      .catch((e) => {
        setStarting(false);
        showToast(`Could not queue: ${(e as Error).message}`);
      });
  };

  const uploadCard = (f: File | undefined) => {
    if (!f || uploadingCard) return;
    setUploadingCard(true);
    void brandingApi
      .upload(f)
      .then((r) => {
        setUploadingCard(false);
        setBrandingFiles((items) =>
          items.some((i) => i.path === r.path) ? items : [...items, { name: r.filename, path: r.path }],
        );
        setLogoPath(r.path);
        showToast(`Ending card saved (${r.filename}).`);
      })
      .catch((e) => {
        setUploadingCard(false);
        showToast(`Could not save card: ${(e as Error).message}`);
      });
  };

  const onTabsKey = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    setUploadTab((t) => {
      if (e.key === "ArrowRight") return t === "browser" ? "server" : "browser";
      return t === "server" ? "browser" : "server";
    });
  };

  const serverChips = isLive ? (
    remotePath ? (
      <>
        <Chip tone="ok">cloud reference</Chip>
        <Chip tone="info">remote</Chip>
        <Chip tone="neutral">validated on queue</Chip>
      </>
    ) : (
    <>
      <Chip tone={pathStat?.exists ? "ok" : "neutral"}>
        {statPending ? "checking…" : pathStat ? (pathStat.exists ? "exists" : "not found") : "no check yet"}
      </Chip>
      <Chip tone={pathStat?.exists ? "info" : "neutral"}>
        {pathStat?.exists ? pathStat.size_human : "size —"}
      </Chip>
      <Chip tone={pathStat?.exists ? "info" : "neutral"}>
        {pathStat?.exists && pathStat.ext ? `${pathStat.ext} · ${pathStat.kind}` : "type —"}
      </Chip>
    </>
    )
  ) : (
    <>
      <Chip tone={serverValid ? "ok" : "neutral"}>{serverValid ? "exists" : "no check yet"}</Chip>
      <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "42.1 MB" : "size —"}</Chip>
      <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "mp3 · audio" : "type —"}</Chip>
    </>
  );

  const summaryBits = [
    uploadTab === "browser"
      ? (isLive ? (fileObj?.name ?? "no file") : (fileName ?? "no file"))
      : serverValid
        ? serverPath.trim()
        : "no path",
    meta.title.trim() || "untitled",
    meta.speaker.trim() || "no speaker",
    meta.date || "no date",
    enhance ? "enhance" : "no enhance",
    transcribe ? "transcribe" : "no transcribe",
    aiMeta ? "ai meta" : "no ai meta",
    dryRun ? "dry run" : "live run",
    autoEdit ? `edit:${autoEditMode}` : "no edit",
    `out:${outputDir}`,
  ];

  return (
    <div className="flex flex-col gap-4 pb-32">
      <PageHeader
        title="New Sermon"
        sub={
          isLive
            ? "Upload, describe, then queue the pipeline on the server."
            : "Upload, describe, then queue the pipeline. Mock only, nothing is sent."
        }
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
            <input
              ref={fileInput}
              type="file"
              accept=".mkv,.mp4,.mov,.webm,.m4v,.mp3,.wav,.m4a,.flac,.ogg,.mpa"
              className="sr-only"
              aria-label="Choose a sermon file"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (isLive) setFileObj(f);
                else if (f) pickMockFile();
              }}
            />
            <div
              role="button"
              tabIndex={0}
              aria-label={
                isLive
                  ? "Drop a sermon file here, or press Enter to choose one"
                  : "Drop a sermon file here, or press Enter to pick a mock file"
              }
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (isLive) {
                  if (f) setFileObj(f);
                } else {
                  pickMockFile();
                }
              }}
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  if (isLive) fileInput.current?.click();
                  else pickMockFile();
                }
              }}
              onClick={() => {
                if (isLive) fileInput.current?.click();
              }}
              className={`flex min-h-[10rem] flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
                dragOver ? "border-accent bg-raised" : "border-line bg-ink"
              }`}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-8 w-8 text-muted" aria-hidden="true">
                <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p className="text-sm font-semibold">
                {isLive ? (fileObj ? `${fileObj.name} (${(fileObj.size / 1048576).toFixed(1)} MB)` : "Drag a file here or choose one") : (fileName ?? "Drag a file here or choose one")}
              </p>
              <p className="text-xs text-muted">
                {isLive
                  ? "Streams to the server ingest area, then queues the real pipeline."
                  : "Files stay local in this mock. Nothing is uploaded."}
              </p>
              <Button
                variant="primary"
                onClick={(e) => {
                  e.stopPropagation();
                  if (isLive) fileInput.current?.click();
                  else pickMockFile();
                }}
              >
                {(isLive ? fileObj : fileName) ? "Replace file" : "Choose file"}
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
            <Field label="Server path" htmlFor="server-path" hint="Absolute path on the processing machine, or a cloud reference remote:<name>:<path> from Settings > Cloud Mounts.">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  id="server-path"
                  value={serverPath}
                  onChange={(e) => setServerPath(e.target.value)}
                  placeholder="/media/sample-sermon.mp3 or remote:drive:sermons/sample.mp3"
                  inputMode="text"
                  autoComplete="off"
                  className={`${inputCls} min-w-0 flex-1`}
                />
                <Button variant="secondary" onClick={() => setLocalOpen(true)}>
                  Browse files
                </Button>
                {remotePath ? (
                  <span
                    className="inline-flex max-w-full items-center gap-1 rounded-full border border-info px-2.5 py-1 text-xs text-info"
                    title={serverPath.trim()}
                  >
                    Cloud file:
                    <span className="truncate font-mono">{serverPath.trim()}</span>
                  </span>
                ) : null}
              </div>
            </Field>
            <div className="flex flex-wrap gap-2" aria-live="polite" aria-label="Path validation">
              {serverChips}
            </div>

            <div className="rounded-md border border-line bg-ink p-3">
              <p className="text-xs font-semibold text-muted">From cloud</p>
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <div className="min-w-[12rem] flex-1">
                  <label htmlFor="cloud-pick" className="sr-only">
                    Cloud remote
                  </label>
                  <select
                    id="cloud-pick"
                    value={cloudPick}
                    onChange={(e) => setCloudPick(e.target.value)}
                    className={inputCls}
                  >
                    <option value="">Choose a remote…</option>
                    {cloudRemotes.map((r) => (
                      <option key={r.name} value={r.name}>
                        {r.name} · {r.provider}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  variant="secondary"
                  onClick={() => setCloudOpen(true)}
                  disabled={!cloudPick}
                >
                  Browse cloud
                </Button>
              </div>
              {cloudRemotes.length === 0 ? (
                <p className="mt-1 text-xs text-muted">
                  No cloud remotes yet. Connect one in Settings › Cloud Mounts.
                </p>
              ) : null}
            </div>

            {isLive ? (
              <p className="text-xs text-muted">
                The server checks the path exists, then queues the real pipeline against it. Nothing is copied.
              </p>
            ) : null}
          </div>
        )}
      </SectionCard>

      <details className="rounded-md border border-line bg-ink p-3">
        <summary className="cursor-pointer text-xs font-semibold text-muted">Output location</summary>
        <p className="mt-2 text-sm">
          Writes to <span className="font-mono text-mist">{outputDir}</span>{" "}
          <span className="text-xs text-muted">
            ({outputSource === "user" ? "your default" : "default"})
          </span>
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => setOutputOpen(true)}>
            Change output location
          </Button>
        </div>
        <p className="mt-1 text-xs text-muted">
          Changing this saves it as your default for future sermons. This run is queued with the
          location chosen here.
        </p>
      </details>

      <SectionCard n={2} title="Metadata" sub="Title, speaker, and date are required. The rest sharpens search and display.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Title (required)" htmlFor="ns-title">
            <input id="ns-title" value={meta.title} onChange={set("title")} placeholder="Sample teaching title" className={inputCls} />
          </Field>
          <Field label="Speaker (required)" htmlFor="ns-speaker">
            <input id="ns-speaker" value={meta.speaker} onChange={set("speaker")} placeholder="Speaker name" autoComplete="off" className={inputCls} />
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
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Toggle checked={enhance} onChange={setEnhance} label="Enhance audio" hint="Noise cleanup before transcription." />
          <Toggle checked={transcribe} onChange={setTranscribe} label="Transcribe" hint="Speech-to-text for captions and search." />
          <Toggle checked={aiMeta} onChange={setAiMeta} label="AI metadata" hint="Draft title, summary, and tags." />
          <Toggle checked={dryRun} onChange={setDryRun} label="Dry run" hint="Process locally, skip the SermonAudio upload." />
        </div>

        <div className="mt-4">
          <Toggle
            checked={autoEdit}
            onChange={setAutoEdit}
            label="Edit Sermon"
            hint="Auto-detect cut points, trim, and fade the video before upload. Video inputs only."
          />
        </div>

        {autoEdit ? (
          <>
            <fieldset className="mt-4">
              <legend className="text-sm font-semibold">Approval mode</legend>
              <div className="mt-2 grid grid-cols-1 gap-2">
                {(
                  [
                    { id: "interactive", label: "Interactive", sub: "Stops at pending review for approval before encode and upload." },
                    { id: "auto", label: "Auto", sub: "Applies automatically when confident; uncertain plans still stop for review." },
                  ] as { id: AutoEditMode; label: string; sub: string }[]
                ).map((o) => (
                  <label key={o.id} className="flex min-h-[44px] cursor-pointer items-start gap-2 rounded-md border border-line p-3">
                    <input
                      type="radio"
                      name="approval-mode"
                      value={o.id}
                      checked={autoEditMode === o.id}
                      onChange={() => setAutoEditMode(o.id)}
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
                {isLive ? " Uploads land in your private branding folder." : ""}
              </p>
              <input
                ref={cardInput}
                type="file"
                accept=".png,.jpg,.jpeg,.webp"
                className="sr-only"
                aria-label="Upload an ending card image"
                onChange={(e) => {
                  uploadCard(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Ending card">
                <button
                  type="button"
                  role="radio"
                  aria-checked={logoPath === "none"}
                  onClick={() => setLogoPath("none")}
                  className={`flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border p-3 text-sm transition-colors ${
                    logoPath === "none" ? "border-accent bg-raised" : "border-line bg-ink hover:border-muted"
                  }`}
                >
                  <span className="font-semibold">No card</span>
                  <span className="text-xs text-muted">fade only</span>
                </button>
                {(isLive ? brandingFiles : []).map((c) => {
                  const selected = logoPath === c.path;
                  return (
                    <button
                      key={c.path}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      aria-label={`Ending card ${c.name}`}
                      onClick={() => setLogoPath(c.path)}
                      className={`flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border p-3 transition-colors ${
                        selected ? "border-accent bg-raised" : "border-line bg-ink hover:border-muted"
                      }`}
                    >
                      <span aria-hidden="true" className="flex h-10 w-16 items-center justify-center overflow-hidden rounded bg-raised font-mono text-xs text-muted">
                        {c.name}
                      </span>
                      <span className="max-w-full truncate text-xs text-muted">{c.name}</span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => (isLive ? cardInput.current?.click() : showToast("Card upload is live-only."))}
                  disabled={uploadingCard}
                  className="flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line p-3 text-sm text-muted transition-colors hover:border-muted hover:text-mist"
                >
                  <span className="font-semibold">{uploadingCard ? "Uploading…" : "Upload new…"}</span>
                  <span className="text-xs">png · jpg · webp</span>
                </button>
              </div>
            </fieldset>

            <div className="mt-3">
              <Toggle checked={fadeBlack} onChange={setFadeBlack} label="Fade to black" hint="Short fade into the ending hold." />
            </div>
          </>
        ) : null}
      </SectionCard>

      <div className="flex flex-col gap-2">
        <Button variant="primary" onClick={start} disabled={!valid || starting} aria-busy={starting} className="w-full sm:w-auto sm:self-start">
          {starting ? "Queueing…" : "Start Processing"}
        </Button>
        <p className="text-xs text-muted" role="status" aria-live="polite">
          {helper}
        </p>
        {queuedJob ? (
          <p className="text-sm">
            <Link to="/jobs" className="font-medium text-accent hover:underline">
              Track job {queuedJob} under Jobs →
            </Link>
          </p>
        ) : null}
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

      {cloudPick ? (
        <CloudFileDialog
          open={cloudOpen}
          name={cloudPick}
          provider={cloudRemotes.find((r) => r.name === cloudPick)?.provider}
          attachedDriveId={cloudRemotes.find((r) => r.name === cloudPick)?.team_drive}
          onClose={() => setCloudOpen(false)}
          onUse={useCloudFile}
        />
      ) : null}

      <FileExplorerDialog
        open={localOpen}
        title="Pick a server file"
        pick="file"
        onPickFile={useLocalFile}
        onClose={() => setLocalOpen(false)}
      />
      <FileExplorerDialog
        open={outputOpen}
        title="Choose an output location"
        pick="folder"
        onPickFolder={pickOutputDir}
        onClose={() => setOutputOpen(false)}
      />

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
