import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  libraryApi,
  outputDirApi,
  serverPathApi,
  uploadApi,
  type ApiCloudFile,
  type ApiCloudRemote,
  type BrandingItem,
  type ServerPathStat,
} from "../api/client";
import { CloudBrowser, MOCK_REMOTES } from "../components/CloudBrowser";
import { Combobox } from "../components/Combobox";
import { FileExplorerDialog } from "../components/FileExplorer";

type SourceKind = "browser" | "server" | "cloud";
type AutoEditMode = "interactive" | "auto";

const sourceOptions: { id: SourceKind; label: string }[] = [
  { id: "browser", label: "Upload" },
  { id: "server", label: "Server path" },
  { id: "cloud", label: "Cloud file" },
];

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const prefilledCloudMatch = (value: string) =>
  /^remote:([A-Za-z0-9._-]{1,64}):(.*)$/.exec(value.trim());

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
  const prefilledCloud = prefilledCloudMatch(prefilledPath);
  const [source, setSource] = useState<SourceKind>(
    prefilledCloud ? "cloud" : prefilledPath ? "server" : "browser",
  );
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [serverPath, setServerPath] = useState(prefilledCloud ? "" : prefilledPath);
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
  const [cloudPick, setCloudPick] = useState(prefilledCloud?.[1] ?? "");
  const [cloudBrowse, setCloudBrowse] = useState("");
  const [cloudFile, setCloudFile] = useState<ApiCloudFile | null>(
    prefilledCloud
      ? {
          name: prefilledCloud[2].split("/").filter(Boolean).pop() ?? prefilledCloud[2],
          path: prefilledCloud[2],
          type: "file",
          size: null,
        }
      : null,
  );
  const [localOpen, setLocalOpen] = useState(false);
  const [outputDir, setOutputDir] = useState("processed_sermons");
  const [outputSource, setOutputSource] = useState<"user" | "default">("default");
  const [outputOpen, setOutputOpen] = useState(false);
  const [outputCloudOpen, setOutputCloudOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const cardInput = useRef<HTMLInputElement>(null);

  const set = (k: keyof typeof initialMeta) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setMeta((m) => ({ ...m, [k]: e.target.value }));

  // Live server-path stat: debounce the input, then ask the server to stat() it.
  useEffect(() => {
    if (!isLive || source !== "server") return;
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
  }, [serverPath, source]);

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

  // Speaker / series suggestions from real sermon history (loaded once per visit).
  const facetsQuery = useQuery({
    queryKey: ["library", "facets"],
    queryFn: () => libraryApi.facets(),
    enabled: isLive,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const facetSpeakerOptions = facetsQuery.data?.speakers ?? [];
  const facetSeriesOptions = facetsQuery.data?.series ?? [];

  const useCloudFile = (item: ApiCloudFile) => {
    setCloudFile(item);
  };

  const chooseCloudRemote = (name: string) => {
    setCloudPick(name);
    setCloudBrowse("");
    setCloudFile(null);
  };

  const useLocalFile = (path: string) => {
    setServerPath(path);
    setLocalOpen(false);
  };

  const saveOutputDir = (next: string) => {
    setOutputDir(next);
    setOutputSource("user");
    if (!isLive) {
      showToast("Output location updated (mock).");
      return;
    }
    void outputDirApi
      .put(next)
      .then((r) => {
        setOutputDir(r.output_dir);
        showToast("Output location saved as your default.");
      })
      .catch((e) => showToast(`Could not save output location: ${(e as Error).message}`));
  };

  const pickOutputDir = (path: string) => {
    setOutputOpen(false);
    saveOutputDir(path);
  };

  const outputRemoteMatch = /^remote:([A-Za-z0-9._-]{1,64}):(.*)$/.exec(outputDir.trim());
  const outputIsCloud = Boolean(outputRemoteMatch);
  const outputRemote = outputRemoteMatch?.[1] ?? "";
  const outputSub = outputRemoteMatch?.[2] ?? "";

  const chooseOutputRemote = (name: string) => {
    if (!name) return;
    saveOutputDir(`remote:${name}:`);
  };

  const pickCloudOutput = (path: string) => {
    setOutputCloudOpen(false);
    const sub = path.replace(/^\/+/, "");
    saveOutputDir(`remote:${outputRemote}:${sub}`);
  };

  const pathLooksValid = serverPath.trim().startsWith("/") && serverPath.trim().length > 3;
  const serverValid = isLive
    ? pathStat
      ? pathStat.exists && pathStat.is_file !== false
      : pathLooksValid
    : pathLooksValid;
  const browserHasSource = isLive ? fileObj !== null : fileName !== null;
  const cloudRef = cloudPick && cloudFile ? `remote:${cloudPick}:${cloudFile.path}` : "";
  const cloudValid = Boolean(cloudRef);
  const hasSource =
    source === "browser" ? browserHasSource : source === "server" ? serverValid : cloudValid;

  const missing = useMemo(() => {
    const list: string[] = [];
    if (!hasSource)
      list.push(
        source === "browser"
          ? "source file"
          : source === "server"
            ? "valid server path"
            : "cloud file",
      );
    if (!meta.title.trim()) list.push("title");
    if (!meta.speaker.trim()) list.push("speaker");
    if (!meta.date) list.push("date");
    return list;
  }, [hasSource, source, meta.title, meta.speaker, meta.date]);

  const valid = missing.length === 0;
  const helper = valid
    ? isLive
      ? "Ready to queue. The pipeline run appears under Jobs."
      : "Source and details are complete. Demo mode sends nothing."
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
    setCloudFile(null);
    setCloudBrowse("");
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
    setCloudFile(null);
    setCloudBrowse("");
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
      showToast("Demo mode: nothing was sent and no job was queued.");
      return;
    }
    setStarting(true);
    if (source === "browser" && fileObj) {
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
    const containerPath = source === "cloud" ? cloudRef : serverPath.trim();
    void serverPathApi
      .create({ container_path: containerPath, ...commonPayload() })
      .then((r) => {
        setStarting(false);
        clearFormKeepJob(r.job_id);
        showToast(`${source === "cloud" ? "Cloud file" : "Server file"} queued as job ${r.job_id}.`);
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
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const index = sourceOptions.findIndex((o) => o.id === source);
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % sourceOptions.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + sourceOptions.length) % sourceOptions.length;
    else if (e.key === "Home") next = 0;
    else next = sourceOptions.length - 1;
    setSource(sourceOptions[next].id);
  };

  const serverChips = isLive ? (
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
  ) : (
    <>
      <Chip tone={serverValid ? "ok" : "neutral"}>{serverValid ? "exists" : "no check yet"}</Chip>
      <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "42.1 MB" : "size —"}</Chip>
      <Chip tone={serverValid ? "info" : "neutral"}>{serverValid ? "mp3 · audio" : "type —"}</Chip>
    </>
  );

  const sourceSummary = (() => {
    if (source === "browser") {
      const name = isLive ? fileObj?.name : fileName;
      const size = isLive ? fileObj?.size : undefined;
      return name ? `upload:${name}${size != null ? ` (${formatBytes(size)})` : ""}` : "upload:no file";
    }
    if (source === "server") {
      if (!serverValid) return "server:no path";
      return `server:${serverPath.trim()}${pathStat?.size_human ? ` (${pathStat.size_human})` : ""}`;
    }
    if (!cloudRef) return "cloud:no file";
    return `cloud:${cloudRef}${cloudFile?.size ? ` (${formatBytes(cloudFile.size)})` : ""}`;
  })();

  const summaryBits = [
    sourceSummary,
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
            : "Upload, describe, then queue the pipeline. Demo mode sends nothing."
        }
        actions={
          <Button variant="ghost" onClick={() => setConfirmReset(true)}>
            Reset
          </Button>
        }
      />

      <SectionCard
        n={1}
        title="Source"
        sub="Pick one source: upload a file, use a path on the server, or choose a file from cloud storage."
      >
        <div
          role="tablist"
          aria-label="Source kind"
          onKeyDown={onTabsKey}
          className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-ink p-1"
        >
          {sourceOptions.map((t) => {
            const selected = source === t.id;
            return (
              <button
                key={t.id}
                id={`source-tab-${t.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`source-panel-${t.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setSource(t.id)}
                className={`flex min-h-[44px] flex-1 items-center justify-center whitespace-nowrap rounded-md px-3 text-sm font-semibold transition-colors ${
                  selected ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {source === "browser" ? (
          <div
            id="source-panel-browser"
            role="tabpanel"
            aria-labelledby="source-tab-browser"
            className="mt-3"
          >
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
              Large files (over ~500 MB) may take a while on slow connections. Prefer Server path or Cloud file for those.
            </p>
            {!browserHasSource ? (
              <p role="alert" className="mt-2 text-xs text-danger">
                Choose a file to upload.
              </p>
            ) : null}
          </div>
        ) : null}

        {source === "server" ? (
          <div
            id="source-panel-server"
            role="tabpanel"
            aria-labelledby="source-tab-server"
            className="mt-3 flex flex-col gap-3"
          >
            <Field
              label="Server path"
              htmlFor="server-path"
              hint="Absolute path on the processing machine."
            >
              <div className="flex flex-wrap items-center gap-2">
                <input
                  id="server-path"
                  value={serverPath}
                  onChange={(e) => setServerPath(e.target.value)}
                  placeholder="/media/sample-sermon.mp3"
                  inputMode="text"
                  autoComplete="off"
                  className={`${inputCls} min-w-0 flex-1`}
                />
                <Button variant="secondary" onClick={() => setLocalOpen(true)}>
                  Browse files
                </Button>
              </div>
            </Field>
            <div className="flex flex-wrap gap-2" aria-live="polite" aria-label="Path validation">
              {serverChips}
            </div>
            {!serverValid ? (
              <p role="alert" className="text-xs text-danger">
                Enter an absolute path that exists on the server.
              </p>
            ) : null}
            {isLive ? (
              <p className="text-xs text-muted">
                The server checks the path exists, then queues the real pipeline against it. Local paths are read in place.
              </p>
            ) : null}
          </div>
        ) : null}

        {source === "cloud" ? (
          <div
            id="source-panel-cloud"
            role="tabpanel"
            aria-labelledby="source-tab-cloud"
            className="mt-3 flex flex-col gap-3"
          >
            <Field
              label="Cloud remote"
              htmlFor="cloud-remote"
              hint="Connect or manage remotes in Settings › Cloud Mounts."
            >
              <select
                id="cloud-remote"
                value={cloudPick}
                onChange={(e) => chooseCloudRemote(e.target.value)}
                className={inputCls}
              >
                <option value="">Choose a remote…</option>
                {cloudRemotes.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name} · {r.provider}
                  </option>
                ))}
              </select>
            </Field>
            {cloudRemotes.length === 0 ? (
              <p className="text-xs text-muted">
                No cloud remotes yet. Connect one in Settings › Cloud Mounts.
              </p>
            ) : null}
            {cloudPick ? (
              <CloudBrowser
                name={cloudPick}
                path={cloudBrowse}
                onPath={setCloudBrowse}
                onUse={useCloudFile}
                provider={cloudRemotes.find((r) => r.name === cloudPick)?.provider}
                attachedDriveId={cloudRemotes.find((r) => r.name === cloudPick)?.team_drive}
              />
            ) : (
              <p className="text-xs text-muted">Choose a remote to browse its files.</p>
            )}
            {cloudRef ? (
              <p className="flex flex-wrap items-center gap-2 text-xs text-info" title={cloudRef}>
                <Chip tone="ok">cloud file</Chip>
                <span className="truncate font-mono">{cloudRef}</span>
                {cloudFile?.size ? (
                  <span className="text-muted">{formatBytes(cloudFile.size)}</span>
                ) : null}
              </p>
            ) : null}
            {!cloudValid ? (
              <p role="alert" className="text-xs text-danger">
                Pick a file with “Use this file”.
              </p>
            ) : null}
            <p className="text-xs text-muted">
              The selected file is fetched into the server's work area for processing, then removed.
            </p>
          </div>
        ) : null}
      </SectionCard>

      <details className="rounded-md border border-line bg-ink p-3">
        <summary className="cursor-pointer text-xs font-semibold text-muted">Output location</summary>
        <p className="mt-2 text-sm">
          {outputIsCloud ? "Cloud" : "Local"}:{" "}
          <span className="font-mono text-mist">{outputDir}</span>{" "}
          <span className="text-xs text-muted">
            ({outputSource === "user" ? "your default" : "default"})
          </span>
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2" aria-live="polite" aria-label="Destination validation">
          {outputIsCloud ? (
            <>
              <Chip tone={outputRemote ? "ok" : "neutral"}>
                {outputRemote ? "cloud remote" : "no remote"}
              </Chip>
              <Chip tone={outputRemote ? "info" : "neutral"}>
                {outputSub ? `folder: ${outputSub}` : "remote root"}
              </Chip>
            </>
          ) : (
            <>
              <Chip tone="ok">local folder</Chip>
              <Chip tone="info">{outputDir || "no path"}</Chip>
            </>
          )}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="output-mode" className="text-xs font-semibold text-muted">
              Destination
            </label>
            <select
              id="output-mode"
              value={outputIsCloud ? "cloud" : "local"}
              onChange={(e) => {
                if (e.target.value === "local") {
                  saveOutputDir("processed_sermons");
                } else if (cloudRemotes[0]) {
                  chooseOutputRemote(cloudRemotes[0].name);
                }
              }}
              className={inputCls}
            >
              <option value="local">Local folder</option>
              <option value="cloud" disabled={cloudRemotes.length === 0}>
                Cloud folder
              </option>
            </select>
          </div>
          {outputIsCloud ? (
            <div>
              <label htmlFor="output-remote" className="text-xs font-semibold text-muted">
                Cloud remote
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  id="output-remote"
                  value={outputRemote}
                  onChange={(e) => chooseOutputRemote(e.target.value)}
                  className={`${inputCls} min-w-0 flex-1`}
                >
                  <option value="">Choose a remote…</option>
                  {cloudRemotes.map((r) => (
                    <option key={r.name} value={r.name}>
                      {r.name} · {r.provider}
                    </option>
                  ))}
                </select>
                <Button
                  variant="secondary"
                  onClick={() => setOutputCloudOpen(true)}
                  disabled={!outputRemote}
                >
                  Browse cloud
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-end">
              <Button variant="secondary" onClick={() => setOutputOpen(true)}>
                Change local folder
              </Button>
            </div>
          )}
        </div>
        <p className="mt-1 text-xs text-muted">
          {outputIsCloud
            ? "Processed files are staged locally, uploaded to the cloud folder with rclone, then the staging copy is removed."
            : "Changing this saves it as your default for future sermons. This run is queued with the location chosen here."}
        </p>
      </details>

      <SectionCard n={2} title="Metadata" sub="Title, speaker, and date are required. The rest sharpens search and display.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Title (required)" htmlFor="ns-title">
            <input id="ns-title" value={meta.title} onChange={set("title")} placeholder="Sample teaching title" className={inputCls} />
          </Field>
          <Field label="Speaker (required)" htmlFor="ns-speaker">
            <Combobox
              id="ns-speaker"
              value={meta.speaker}
              onChange={(value) => setMeta((m) => ({ ...m, speaker: value }))}
              options={facetSpeakerOptions}
              placeholder="Speaker name"
              ariaLabel="Speaker"
              className={inputCls}
              required
            />
          </Field>
          <Field label="Date (required)" htmlFor="ns-date">
            <input id="ns-date" type="date" value={meta.date} onChange={set("date")} className={inputCls} />
          </Field>
          <Field label="Series" htmlFor="ns-series">
            <Combobox
              id="ns-series"
              value={meta.series}
              onChange={(value) => setMeta((m) => ({ ...m, series: value }))}
              options={facetSeriesOptions}
              placeholder="Sample Series A"
              ariaLabel="Series"
              className={inputCls}
            />
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
      {outputRemote ? (
        <FileExplorerDialog
          open={outputCloudOpen}
          title="Choose a cloud output folder"
          mode="cloud"
          name={outputRemote}
          pick="folder"
          onPickFolder={pickCloudOutput}
          onClose={() => setOutputCloudOpen(false)}
        />
      ) : null}

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
