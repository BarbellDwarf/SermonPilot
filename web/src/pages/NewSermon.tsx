import { useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, UNSAFE_DataRouterContext, useSearchParams } from "react-router-dom";
import {
  Button,
  Chip,
  ConfirmDialog,
  Field,
  Icon,
  Menu,
  PageHeader,
  SectionCard,
  Toggle,
  buttonClass,
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
import { IntakeUnsavedChangesDialog } from "../components/intake/IntakeUnsavedChangesDialog";
import { RunSummary } from "../components/intake/RunSummary";
import { useToast } from "../components/toast";
import { useUserSettings } from "../api/useUserSettings";
import { formatBytes } from "../utils/format";

type SourceKind = "browser" | "server" | "cloud";
type AutoEditMode = "interactive" | "auto";
type FieldKey = "source" | "title" | "speaker" | "date";

const sourceOptions: { id: SourceKind; label: string }[] = [
  { id: "browser", label: "Upload" },
  { id: "server", label: "Server path" },
  { id: "cloud", label: "Cloud file" },
];

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
const fileAccept = ".mkv,.mp4,.mov,.webm,.m4v,.mp3,.wav,.m4a,.flac,.ogg,.mpa";
const acceptedFormats = Array.from(
  new Set(fileAccept.split(",").map((format) => format.trim().replace(/^\./, "").toUpperCase())),
);

interface IntakeDefaults {
  eventType: string;
  enhance: boolean;
  transcribe: boolean;
  generateMetadata: boolean;
  dryRun: boolean;
  autoEdit: boolean;
  autoEditMode: AutoEditMode;
  logoPath: string;
  fadeBlack: boolean;
}

const defaultRun: IntakeDefaults = {
  eventType: "Sunday Service",
  enhance: true,
  transcribe: true,
  generateMetadata: true,
  dryRun: false,
  autoEdit: false,
  autoEditMode: "interactive",
  logoPath: "none",
  fadeBlack: true,
};

const initialMeta = {
  title: "",
  speaker: "",
  date: "",
  series: "",
  eventType: defaultRun.eventType,
  scripture: "",
};

export function NewSermon() {
  const notify = useToast();
  const [searchParams] = useSearchParams();
  const hasDataRouter = useContext(UNSAFE_DataRouterContext) !== null;
  const [savedRunDefaults, saveRunDefaults, defaultsLoaded] = useUserSettings<IntakeDefaults>(
    "intake.defaults",
    defaultRun,
  );
  const [dirty, setDirty] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const appliedDefaults = useRef(false);
  const defaultOutputDir = useRef("processed_sermons");
  const defaultOutputSource = useRef<"user" | "default">("default");
  const outputDirty = useRef(false);
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
  const [touched, setTouched] = useState<Record<FieldKey, boolean>>({
    source: false,
    title: false,
    speaker: false,
    date: false,
  });
  const [enhance, setEnhance] = useState(defaultRun.enhance);
  const [transcribe, setTranscribe] = useState(defaultRun.transcribe);
  const [generateMetadata, setGenerateMetadata] = useState(defaultRun.generateMetadata);
  const [dryRun, setDryRun] = useState(defaultRun.dryRun);
  const [autoEdit, setAutoEdit] = useState(defaultRun.autoEdit);
  const [autoEditMode, setAutoEditMode] = useState<AutoEditMode>(defaultRun.autoEditMode);
  const [logoPath, setLogoPath] = useState<string>(defaultRun.logoPath);
  const [brandingFiles, setBrandingFiles] = useState<BrandingItem[]>([]);
  const [uploadingCard, setUploadingCard] = useState(false);
  const [fadeBlack, setFadeBlack] = useState(defaultRun.fadeBlack);
  const [confirmReset, setConfirmReset] = useState(false);
  const [starting, setStarting] = useState(false);
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
  const [outputSource, setOutputSource] = useState<"user" | "default" | "run">("default");
  const [outputOpen, setOutputOpen] = useState(false);
  const [outputCloudOpen, setOutputCloudOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const cardInput = useRef<HTMLInputElement>(null);

  const set = (k: keyof typeof initialMeta) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setMeta((m) => ({ ...m, [k]: e.target.value }));

  const markDirty = () => {
    setDirty(true);
    setSubmitted(false);
  };

  useEffect(() => {
    if (!defaultsLoaded || appliedDefaults.current) return;
    appliedDefaults.current = true;
    if (dirty) return;
    setMeta((m) => ({ ...m, eventType: savedRunDefaults.eventType }));
    setEnhance(savedRunDefaults.enhance);
    setTranscribe(savedRunDefaults.transcribe);
    setGenerateMetadata(savedRunDefaults.generateMetadata);
    setDryRun(savedRunDefaults.dryRun);
    setAutoEdit(savedRunDefaults.autoEdit);
    setAutoEditMode(savedRunDefaults.autoEditMode);
    setLogoPath(savedRunDefaults.logoPath);
    setFadeBlack(savedRunDefaults.fadeBlack);
  }, [defaultsLoaded, dirty, savedRunDefaults]);

  // Live server-path stat: debounce the input, then ask the server to stat() it.
  useEffect(() => {
    if (!isLive || source !== "server") return;
    const trimmed = serverPath.trim();
    if (!trimmed.startsWith("/") || trimmed.length <= 3) {
      setPathStat(null);
      setStatPending(false);
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
        defaultOutputDir.current = r.output_dir;
        defaultOutputSource.current = r.source;
        if (!outputDirty.current) {
          setOutputDir(r.output_dir);
          setOutputSource(r.source);
        }
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
    markDirty();
    setCloudFile(item);
  };

  const chooseCloudRemote = (name: string) => {
    setCloudPick(name);
    setCloudBrowse("");
    setCloudFile(null);
  };

  const useLocalFile = (path: string) => {
    markDirty();
    setServerPath(path);
    setLocalOpen(false);
  };

  const setRunOutputDir = (next: string) => {
    markDirty();
    outputDirty.current = true;
    setOutputDir(next);
    setOutputSource("run");
  };

  const pickOutputDir = (path: string) => {
    setOutputOpen(false);
    setRunOutputDir(path);
  };

  const outputRemoteMatch = /^remote:([A-Za-z0-9._-]{1,64}):(.*)$/.exec(outputDir.trim());
  const outputIsCloud = Boolean(outputRemoteMatch);
  const outputRemote = outputRemoteMatch?.[1] ?? "";
  const outputSub = outputRemoteMatch?.[2] ?? "";

  const chooseOutputRemote = (name: string) => {
    if (!name) return;
    setRunOutputDir(`remote:${name}:`);
  };

  const pickCloudOutput = (path: string) => {
    setOutputCloudOpen(false);
    const sub = path.replace(/^\/+/, "");
    setRunOutputDir(`remote:${outputRemote}:${sub}`);
  };

  const saveAsDefault = async () => {
    if (savingDefaults) return;
    setSavingDefaults(true);
    try {
      await saveRunDefaults({
        eventType: meta.eventType || defaultRun.eventType,
        enhance,
        transcribe,
        generateMetadata,
        dryRun,
        autoEdit,
        autoEditMode,
        logoPath,
        fadeBlack,
      });
    } catch (e) {
      showToast(`Could not save run defaults: ${(e as Error).message}`, "error");
      setSavingDefaults(false);
      return;
    }
    try {
      if (isLive) {
        const result = await outputDirApi.put(outputDir);
        defaultOutputDir.current = result.output_dir;
        defaultOutputSource.current = result.source;
        setOutputDir(result.output_dir);
        setOutputSource(result.source);
      } else {
        defaultOutputDir.current = outputDir;
        defaultOutputSource.current = outputSource === "run" ? "user" : outputSource;
      }
      showToast(isLive ? "Saved as your default." : "Defaults saved for this demo session.");
    } catch (e) {
      showToast(`Run defaults saved, but the output folder could not be saved: ${(e as Error).message}`, "error");
    } finally {
      setSavingDefaults(false);
    }
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
      ? "Ready to queue. The pipeline run appears under Activity."
      : "Source and details are complete. Demo mode sends nothing."
    : `Still needed: ${missing.join(", ")}.`;

  const touch = (key: FieldKey) => setTouched((t) => (t[key] ? t : { ...t, [key]: true }));
  const titleError = touched.title && !meta.title.trim();
  const speakerError = touched.speaker && !meta.speaker.trim();
  const dateError = touched.date && !meta.date;
  const sourceError = touched.source && !hasSource;

  const pickMockFile = () => {
    markDirty();
    setFileName("sample-sermon-upload.mp3");
  };

  const showToast = (
    msg: string,
    variant: "success" | "error" | "info" = "success",
  ) => notify[variant](msg);

  const resetRunOptions = () => {
    setMeta({ ...initialMeta, eventType: savedRunDefaults.eventType });
    setTouched({ source: false, title: false, speaker: false, date: false });
    setEnhance(savedRunDefaults.enhance);
    setTranscribe(savedRunDefaults.transcribe);
    setGenerateMetadata(savedRunDefaults.generateMetadata);
    setDryRun(savedRunDefaults.dryRun);
    setAutoEdit(savedRunDefaults.autoEdit);
    setAutoEditMode(savedRunDefaults.autoEditMode);
    setLogoPath(savedRunDefaults.logoPath);
    setFadeBlack(savedRunDefaults.fadeBlack);
  };

  const resetAll = () => {
    setFileName(null);
    setFileObj(null);
    setQueuedJob(null);
    setServerPath("");
    setPathStat(null);
    setCloudFile(null);
    setCloudBrowse("");
    if (fileInput.current) fileInput.current.value = "";
    outputDirty.current = false;
    setOutputDir(defaultOutputDir.current);
    setOutputSource(defaultOutputSource.current);
    resetRunOptions();
    setDirty(false);
    setSubmitted(false);
  };

  const clearFormKeepJob = (jobId: string) => {
    setFileName(null);
    setFileObj(null);
    setQueuedJob(jobId);
    setServerPath("");
    setPathStat(null);
    setCloudFile(null);
    setCloudBrowse("");
    if (fileInput.current) fileInput.current.value = "";
    resetRunOptions();
    setDirty(false);
    setSubmitted(true);
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
    skip_ai_generation: !generateMetadata,
    dry_run: dryRun,
    auto_edit_enabled: autoEdit,
    auto_edit_mode: autoEdit ? autoEditMode : null,
    logo_path: logoPath === "none" ? "" : logoPath,
    fade_to_black: fadeBlack,
    output_dir: outputDir,
  });

  const focusFirstInvalid = () => {
    const targetId = !hasSource
      ? source === "browser"
        ? "ns-choose-file"
        : source === "server"
          ? "server-path"
          : "cloud-remote"
      : !meta.title.trim()
        ? "ns-title"
        : !meta.speaker.trim()
          ? "ns-speaker"
          : "ns-date";
    document.getElementById(targetId)?.focus();
  };

  const start = (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid || starting) {
      if (!valid) {
        setTouched({ source: true, title: true, speaker: true, date: true });
        window.setTimeout(focusFirstInvalid, 0);
      }
      return;
    }
    setSubmitted(true);
    if (!isLive) {
      showToast("Demo mode: nothing was sent.", "info");
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
          setSubmitted(false);
          showToast(`Could not queue: ${(e as Error).message}`, "error");
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
        setSubmitted(false);
        showToast(`Could not queue: ${(e as Error).message}`, "error");
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
        showToast(`Could not save card: ${(e as Error).message}`, "error");
      });
  };

  const onSourceChange = (next: SourceKind) => {
    setSource(next);
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
      return name
        ? `Upload · ${name}${size != null ? ` (${formatBytes(size)})` : ""}`
        : "Upload · no file";
    }
    if (source === "server") {
      if (!serverValid) return "Server path · not set";
      return `Server path · ${serverPath.trim()}${pathStat?.size_human ? ` (${pathStat.size_human})` : ""}`;
    }
    if (!cloudRef) return "Cloud · no file";
    return `Cloud · ${cloudPick}/${cloudFile?.path ?? ""}${cloudFile?.size ? ` (${formatBytes(cloudFile.size)})` : ""}`;
  })();

  const outputSummary = outputIsCloud
    ? `Cloud · ${outputRemote}${outputSub ? `/${outputSub}` : " · remote root"}`
    : `Local · ${outputDir || "not set"}`;
  const processingSummary = [
    enhance ? "Audio enhancement" : "Original audio",
    transcribe ? "Transcription" : "No transcription",
    generateMetadata ? "Metadata generated" : "Metadata left as entered",
    autoEdit ? `Auto-edit · ${autoEditMode === "auto" ? "automatic" : "interactive review"}` : "No auto-edit",
  ].join(" · ");

  return (
    <div className="flex flex-col gap-4 pb-4">
      <PageHeader
        title="New teaching"
        actions={
          <Menu
            label="More actions"
            trigger="More actions"
            triggerTestId="new-teaching-more"
            triggerClassName={buttonClass("secondary")}
            items={[
              {
                label: "Reset form",
                onSelect: () => setConfirmReset(true),
                danger: true,
                testId: "new-teaching-reset",
              },
            ]}
          />
        }
      />

      <form
        aria-label="New teaching"
        noValidate
        onSubmit={start}
        onChangeCapture={markDirty}
        className="pb-44 lg:pb-4"
      >
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
          <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        n={1}
        title="Source"
        sub="Pick one source, then choose the file for that source."
      >
        <Field label="Source" htmlFor="source-kind">
          <select
            id="source-kind"
            value={source}
            onChange={(e) => onSourceChange(e.target.value as SourceKind)}
            className={inputCls}
          >
            {sourceOptions.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>

        {source === "browser" ? (
          <section id="source-panel-browser" className="mt-3">
            <input
              ref={fileInput}
              type="file"
              accept={fileAccept}
              className="sr-only"
              tabIndex={-1}
              aria-label="Choose a teaching file"
              aria-invalid={sourceError || undefined}
              aria-describedby={sourceError ? "ns-source-error" : undefined}
              onBlur={() => touch("source")}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (isLive) setFileObj(f);
                else if (f) pickMockFile();
              }}
            />
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                touch("source");
                const f = e.dataTransfer.files?.[0];
                if (isLive) {
                  if (f) {
                    markDirty();
                    setFileObj(f);
                  }
                } else {
                  pickMockFile();
                }
              }}
              className={`flex min-h-[10rem] flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
                dragOver ? "border-accent bg-raised" : "border-line bg-ink"
              }`}
            >
              <Icon name="upload" className="h-8 w-8 text-muted" />
              <p className="text-sm font-semibold">
                {isLive ? (fileObj ? `${fileObj.name} (${formatBytes(fileObj.size)})` : "Drag a file here or choose one") : (fileName ?? "Drag a file here or choose one")}
              </p>
              <p className="text-xs text-muted">
                {isLive
                  ? "Streams to the server ingest area, then queues the real pipeline."
                  : "Files stay local in this demo. Nothing is uploaded."}
              </p>
              <Button
                id="ns-choose-file"
                variant="secondary"
                aria-describedby={sourceError ? "ns-source-error" : undefined}
                onClick={() => {
                  touch("source");
                  if (isLive) fileInput.current?.click();
                  else pickMockFile();
                }}
              >
                {(isLive ? fileObj : fileName) ? "Replace file" : "Choose file"}
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Supported formats">
              {acceptedFormats.map((f) => (
                <Chip key={f} tone="neutral">
                  {f}
                </Chip>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">
              Large files (over ~500 MB) may take a while on slow connections. Prefer Server path or Cloud file for those.
            </p>
            {sourceError ? (
              <p id="ns-source-error" className="mt-2 text-xs text-danger">
                Choose a file to upload.
              </p>
            ) : null}
          </section>
        ) : null}

        {source === "server" ? (
          <section id="source-panel-server" className="mt-3 flex flex-col gap-3">
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
                  onBlur={() => touch("source")}
                  aria-invalid={sourceError || undefined}
                  aria-describedby={sourceError ? "ns-server-error" : undefined}
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
            {sourceError ? (
              <p id="ns-server-error" className="text-xs text-danger">
                Enter an absolute path that exists on the server.
              </p>
            ) : null}
            {isLive ? (
              <p className="text-xs text-muted">
                The server checks the path exists, then queues the real pipeline against it. Local paths are read in place.
              </p>
            ) : null}
          </section>
        ) : null}

        {source === "cloud" ? (
          <section id="source-panel-cloud" className="mt-3 flex flex-col gap-3">
            <Field
              label="Cloud remote"
              htmlFor="cloud-remote"
              hint="Connect or manage remotes in Settings › Cloud Mounts."
            >
              <select
                id="cloud-remote"
                value={cloudPick}
                onChange={(e) => chooseCloudRemote(e.target.value)}
                onBlur={() => touch("source")}
                aria-invalid={sourceError || undefined}
                aria-describedby={sourceError ? "ns-cloud-error" : undefined}
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
            {sourceError ? (
              <p id="ns-cloud-error" className="text-xs text-danger">
                Pick a file with “Use this file”.
              </p>
            ) : null}
            <p className="text-xs text-muted">
              The selected file is fetched into the server's work area for processing, then removed.
            </p>
          </section>
        ) : null}
      </SectionCard>

      <SectionCard n={2} title="Metadata" sub="Title, speaker, and date are required. The rest sharpens search and display.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Title (required)" htmlFor="ns-title">
            <input
              id="ns-title"
              value={meta.title}
              onChange={set("title")}
              onBlur={() => touch("title")}
              aria-invalid={titleError || undefined}
              aria-describedby={titleError ? "ns-title-error" : undefined}
              placeholder="Sample teaching title"
              className={inputCls}
            />
            {titleError ? (
              <p id="ns-title-error" className="mt-1 text-xs text-danger">
                Add a title.
              </p>
            ) : null}
          </Field>
          <Field label="Speaker (required)" htmlFor="ns-speaker">
            <div onBlur={() => touch("speaker")}>
              <Combobox
                id="ns-speaker"
                value={meta.speaker}
                onChange={(value) => setMeta((m) => ({ ...m, speaker: value }))}
                options={facetSpeakerOptions}
                placeholder="Speaker name"
                ariaLabel="Speaker"
                className={inputCls}
                required
                invalid={speakerError}
                describedBy={speakerError ? "ns-speaker-error" : undefined}
              />
              {speakerError ? (
                <p id="ns-speaker-error" className="mt-1 text-xs text-danger">
                  Add a speaker.
                </p>
              ) : null}
            </div>
          </Field>
          <Field label="Date (required)" htmlFor="ns-date">
            <input
              id="ns-date"
              type="date"
              value={meta.date}
              onChange={set("date")}
              onBlur={() => touch("date")}
              aria-invalid={dateError || undefined}
              aria-describedby={dateError ? "ns-date-error" : undefined}
              className={inputCls}
            />
            {dateError ? (
              <p id="ns-date-error" className="mt-1 text-xs text-danger">
                Add the recording date.
              </p>
            ) : null}
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
          <Field label="Scripture" htmlFor="ns-scripture" hint="Free text, e.g. Psalm 23">
            <input id="ns-scripture" value={meta.scripture} onChange={set("scripture")} placeholder="Psalm 23" className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard n={3} title="Processing options" sub="These choices apply to this run. Save them as your default when they should carry forward.">
        <fieldset className="rounded-md border border-line p-3">
          <legend className="px-1 text-sm font-semibold">For this run</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Event type" htmlFor="ns-event">
              <select id="ns-event" value={meta.eventType} onChange={set("eventType")} className={inputCls}>
                {eventTypes.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Destination" htmlFor="output-mode">
              <select
                id="output-mode"
                value={outputIsCloud ? "cloud" : "local"}
                onChange={(e) => {
                  if (e.target.value === "local") {
                    setRunOutputDir(defaultOutputDir.current);
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
            </Field>
            <div className="sm:col-span-2">
              <p className="text-sm">
                <span className="font-semibold">{outputIsCloud ? "Cloud" : "Local"}</span>
                {" · "}
                <span className="break-all">{outputDir || "No output folder"}</span>
                <span className="ml-2 text-xs text-muted">
                  {outputSource === "run"
                    ? "changed for this run"
                    : outputSource === "user"
                      ? "your default"
                      : "default"}
                </span>
              </p>
              {outputIsCloud ? (
                <div className="mt-2 flex flex-wrap items-end gap-2">
                  <Field label="Cloud remote" htmlFor="output-remote">
                    <select
                      id="output-remote"
                      value={outputRemote}
                      onChange={(e) => chooseOutputRemote(e.target.value)}
                      className={`${inputCls} min-w-0`}
                    >
                      <option value="">Choose a remote…</option>
                      {cloudRemotes.map((r) => (
                        <option key={r.name} value={r.name}>
                          {r.name} · {r.provider}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Button
                    variant="secondary"
                    onClick={() => setOutputCloudOpen(true)}
                    disabled={!outputRemote}
                  >
                    Browse cloud
                  </Button>
                </div>
              ) : (
                <div className="mt-2">
                  <Button variant="secondary" onClick={() => setOutputOpen(true)}>
                    Change local folder
                  </Button>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-3">
            <p className="text-sm font-semibold">Pipeline stages</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Toggle checked={enhance} onChange={(v) => { markDirty(); setEnhance(v); }} label="Enhance audio" hint="Noise cleanup before transcription." />
              <Toggle checked={transcribe} onChange={(v) => { markDirty(); setTranscribe(v); }} label="Transcribe" hint="Speech-to-text for captions and search." />
              <Toggle
                checked={generateMetadata}
                onChange={(v) => { markDirty(); setGenerateMetadata(v); }}
                label="Generate metadata on upload"
                hint="Fill any empty title, summary, and tags from the transcript."
              />
              <Toggle
                checked={autoEdit}
                onChange={(v) => { markDirty(); setAutoEdit(v); }}
                label="Edit teaching"
                hint="Auto-detect cut points, trim, and fade the video before upload. Video inputs only."
              />
              <div className="sm:col-span-2">
                <Toggle
                  checked={dryRun}
                  onChange={(v) => { markDirty(); setDryRun(v); }}
                  label="Dry run"
                  hint="Process locally and skip the SermonAudio upload. Off by default."
                />
              </div>
            </div>
          </div>

        {autoEdit ? (
          <div className="mt-4 flex flex-col gap-3">
            <fieldset>
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

            <fieldset>
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
                  onClick={() => {
                    markDirty();
                    setLogoPath("none");
                  }}
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
                      onClick={() => {
                        markDirty();
                        setLogoPath(c.path);
                      }}
                      className={`flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border p-3 transition-colors ${
                        selected ? "border-accent bg-raised" : "border-line bg-ink hover:border-muted"
                      }`}
                    >
                      <span aria-hidden="true" className="flex h-10 w-16 items-center justify-center overflow-hidden rounded-sm bg-raised font-mono text-xs text-muted">
                        {c.name}
                      </span>
                      <span className="max-w-full truncate text-xs text-muted">{c.name}</span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => (isLive ? cardInput.current?.click() : showToast("Card upload is live-only.", "info"))}
                  disabled={uploadingCard}
                  className="flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line p-3 text-sm text-muted transition-colors hover:border-muted hover:text-mist"
                >
                  <span className="font-semibold">{uploadingCard ? "Uploading…" : "Upload new…"}</span>
                  <span className="text-xs">png · jpg · webp</span>
                </button>
              </div>
            </fieldset>

            <Toggle checked={fadeBlack} onChange={(v) => { markDirty(); setFadeBlack(v); }} label="Fade to black" hint="Short fade into the ending hold." />
          </div>
        ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <Button
              variant="secondary"
              onClick={() => void saveAsDefault()}
              disabled={savingDefaults || !defaultsLoaded}
            >
              {savingDefaults ? "Saving…" : defaultsLoaded ? "Save as my default" : "Loading defaults…"}
            </Button>
            <p className="max-w-prose text-xs text-muted">
              Stores the event type, output folder, dry run, and pipeline choices for the next teaching.
            </p>
          </div>
        </fieldset>
      </SectionCard>

      {queuedJob ? (
        <p className="text-sm">
          <Link to="/activity" className="font-medium text-accent hover:underline">
            Track job {queuedJob} under Activity →
          </Link>
        </p>
      ) : null}

          </div>
          <RunSummary
            source={sourceSummary}
            title={meta.title.trim() || "Not set"}
            speaker={meta.speaker.trim() || "Not set"}
            date={meta.date || "Not set"}
            eventType={meta.eventType || defaultRun.eventType}
            output={outputSummary}
            dryRun={dryRun}
            processing={processingSummary}
            readiness={helper}
            starting={starting}
            valid={valid}
          />
        </div>
      </form>

      {hasDataRouter ? (
        <IntakeUnsavedChangesDialog when={dirty && !submitted} suppressed={confirmReset} />
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
    </div>
  );
}
