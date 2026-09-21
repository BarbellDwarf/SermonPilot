import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  filesApi,
  isLive,
  type ApiExploreResult,
  type ApiFileEntry,
} from "../api/client";
import { Button, Chip } from "./ui";
import { CloudBrowser, formatModified, sortNewestFirst } from "./CloudBrowser";

export type ExplorerMode = "local" | "cloud";
export type PickMode = "file" | "folder";

export interface FileExplorerProps {
  mode?: ExplorerMode;
  name?: string;
  path: string;
  onPath: (p: string) => void;
  onUseFile?: (path: string) => void;
  onUseFolder?: (path: string) => void;
  pick?: PickMode;
}

const MOCK_LOCAL: Record<string, ApiFileEntry[]> = {
  "/": [
    { name: "sermons", path: "/sermons", type: "dir", size: null, modified: "2026-09-20T20:47:00" },
    {
      name: "sample-sermon.mp3",
      path: "/sample-sermon.mp3",
      type: "file",
      size: 42_100_000,
      modified: "2026-09-20T20:47:00",
    },
  ],
  "/sermons": [
    { name: "2026", path: "/sermons/2026", type: "dir", size: null, modified: "2026-09-19T09:00:00" },
    {
      name: "old-sermon.mp3",
      path: "/sermons/old-sermon.mp3",
      type: "file",
      size: 38_000_000,
      modified: "2026-09-01T08:00:00",
    },
  ],
  "/sermons/2026": [
    {
      name: "september.mp3",
      path: "/sermons/2026/september.mp3",
      type: "file",
      size: 51_200_000,
      modified: "2026-09-14T11:30:00",
    },
  ],
};

function mockExplore(path: string): ApiExploreResult {
  const current = path || "/";
  const segments = current.split("/").filter(Boolean);
  const parent = segments.length > 1 ? `/${segments.slice(0, -1).join("/")}` : current === "/" ? null : "/";
  return {
    path: current,
    parent,
    root: "/",
    roots: [{ name: "processed_sermons", path: "/" }],
    items: MOCK_LOCAL[current] ?? [],
  };
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function LocalExplorer({ path, onPath, onUseFile, onUseFolder, pick = "file" }: FileExplorerProps) {
  const query = useQuery({
    queryKey: ["files", "explore", path],
    queryFn: () => (isLive ? filesApi.explore(path) : Promise.resolve(mockExplore(path))),
    staleTime: 5_000,
  });
  const data = query.data;
  const root = data?.root ?? "";
  const relative =
    data && data.path.startsWith(root) ? data.path.slice(root.length).replace(/^\/+/, "") : "";
  const crumbs = relative ? relative.split("/") : [];
  const rootLabel = root.split("/").filter(Boolean).pop() ?? "root";
  const items = sortNewestFirst(data?.items ?? [], (item) => item.type === "dir");

  return (
    <div className="mt-3 rounded-lg border border-line bg-ink p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">Browsing local server files</p>
        <div className="flex flex-wrap gap-2">
          {pick === "folder" && data?.path ? (
            <Button variant="primary" onClick={() => onUseFolder?.(data.path)}>
              Use this folder
            </Button>
          ) : null}
          <Button onClick={() => onPath(data?.parent ?? "")} disabled={!data?.parent}>
            Up one level
          </Button>
        </div>
      </div>
      <p className="mt-1 text-xs text-muted">
        {pick === "file" ? (
          <>
            Pick a file, then choose <span className="font-semibold text-mist">Use this file</span>.
          </>
        ) : (
          <>
            Pick a folder, then choose{" "}
            <span className="font-semibold text-mist">Use this folder</span>.
          </>
        )}
      </p>

      {data && data.roots.length > 1 ? (
        <div className="mt-2 flex flex-wrap gap-1" aria-label="Allowed roots">
          {data.roots.map((r) => {
            const active = data.path === r.path || data.path.startsWith(`${r.path}/`);
            return (
              <button
                key={r.path}
                type="button"
                onClick={() => onPath(r.path)}
                aria-pressed={active}
                className={`rounded px-2 py-1 font-mono text-xs ${
                  active ? "bg-raised text-mist" : "text-muted hover:text-mist"
                }`}
                title={r.path}
              >
                {r.name}
              </button>
            );
          })}
        </div>
      ) : null}

      <nav aria-label="Folder path" className="mt-2 flex flex-wrap items-center gap-1 text-xs">
        <button
          type="button"
          onClick={() => onPath(root)}
          className="rounded px-1 font-mono text-muted hover:text-mist"
        >
          {rootLabel}
        </button>
        {crumbs.map((seg, i) => (
          <span key={`${seg}-${i}`} className="flex items-center gap-1">
            <span aria-hidden="true" className="text-muted">
              /
            </span>
            <button
              type="button"
              onClick={() => onPath(`${root}/${crumbs.slice(0, i + 1).join("/")}`)}
              className="rounded px-1 font-mono text-muted hover:text-mist"
            >
              {seg}
            </button>
          </span>
        ))}
      </nav>

      {query.isError ? (
        <p role="alert" className="mt-3 rounded-md border border-danger px-3 py-2 text-xs text-danger">
          {(query.error as Error).message}
        </p>
      ) : query.isPending ? (
        <p className="mt-3 text-xs text-muted" role="status">
          Loading folder…
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-xs text-muted">This folder is empty.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-line">
          {items.map((item) => (
            <li key={item.path} className="flex flex-wrap items-center gap-2 py-2">
              <Chip tone="neutral">{item.type === "dir" ? "folder" : "file"}</Chip>
              {item.type === "dir" ? (
                <>
                  <button
                    type="button"
                    onClick={() => onPath(item.path)}
                    className="min-w-0 flex-1 truncate rounded px-1 text-left text-sm hover:text-accent"
                  >
                    {item.name}
                  </button>
                  {pick === "folder" ? (
                    <Button variant="primary" onClick={() => onUseFolder?.(item.path)}>
                      Use this folder
                    </Button>
                  ) : null}
                </>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate px-1 text-sm">{item.name}</span>
                  <span className="font-mono text-xs text-muted">
                    {formatModified(item.modified)}
                  </span>
                  {item.size === 0 ? (
                    <span className="font-mono text-xs text-muted">empty file</span>
                  ) : (
                    <span className="font-mono text-xs text-muted">{formatSize(item.size)}</span>
                  )}
                  {pick === "file" ? (
                    <Button
                      variant="primary"
                      disabled={item.size === 0}
                      title={
                        item.size === 0
                          ? "This file is 0 bytes and cannot be processed"
                          : undefined
                      }
                      onClick={() => onUseFile?.(item.path)}
                    >
                      Use this file
                    </Button>
                  ) : null}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FileExplorer(props: FileExplorerProps) {
  if ((props.mode ?? "local") === "cloud") {
    return (
      <CloudBrowser
        name={props.name ?? ""}
        path={props.path}
        pick={props.pick}
        onPath={props.onPath}
        onUse={(item) => props.onUseFile?.(item.path)}
        onUseFolder={(p) => props.onUseFolder?.(p)}
      />
    );
  }
  return <LocalExplorer {...props} />;
}

export function FileExplorerDialog({
  open,
  title,
  mode = "local",
  name,
  pick = "file",
  startPath = "",
  onPickFile,
  onPickFolder,
  onClose,
}: {
  open: boolean;
  title: string;
  mode?: ExplorerMode;
  name?: string;
  pick?: PickMode;
  startPath?: string;
  onPickFile?: (path: string) => void;
  onPickFolder?: (path: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [path, setPath] = useState(startPath);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  useEffect(() => {
    if (open) setPath(startPath);
  }, [open, startPath]);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="w-[min(44rem,calc(100vw-2rem))] max-h-[85vh] overflow-y-auto rounded-xl border border-line bg-surface p-4 text-mist backdrop:bg-black/60"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <Button onClick={onClose}>Close</Button>
      </div>
      {open ? (
        <FileExplorer
          mode={mode}
          name={name}
          path={path}
          pick={pick}
          onPath={setPath}
          onUseFile={(p) => {
            onPickFile?.(p);
            onClose();
          }}
          onUseFolder={(p) => {
            onPickFolder?.(p);
            onClose();
          }}
        />
      ) : null}
    </dialog>
  );
}
