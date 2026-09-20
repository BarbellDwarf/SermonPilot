import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { cloudApi, isLive, type ApiCloudFile, type ApiCloudRemote, type ApiSharedDrive } from "../api/client";
import { Button, Chip } from "./ui";

export let MOCK_REMOTES: ApiCloudRemote[] = [
  { name: "sermons-drive", provider: "drive", status: "configured" },
];

export function mockAddRemote(name: string, provider: string): ApiCloudRemote {
  const remote: ApiCloudRemote = { name, provider, status: "configured" };
  MOCK_REMOTES = [...MOCK_REMOTES.filter((r) => r.name !== name), remote];
  return remote;
}

export function mockRemoveRemote(name: string): void {
  MOCK_REMOTES = MOCK_REMOTES.filter((r) => r.name !== name);
}

export const MOCK_SHARED_DRIVES: ApiSharedDrive[] = [
  { id: "0ABCdef", name: "Church Media" },
  { id: "0GHIjkl", name: "Archives" },
];

export function mockAttachSharedDrive(name: string, driveId: string): void {
  MOCK_REMOTES = MOCK_REMOTES.map((r) => (r.name === name ? { ...r, team_drive: driveId } : r));
}

export function mockDetachSharedDrive(name: string): void {
  MOCK_REMOTES = MOCK_REMOTES.map((r) => {
    if (r.name !== name) return r;
    const next = { ...r };
    delete next.team_drive;
    return next;
  });
}

const MOCK_TREE: Record<string, ApiCloudFile[]> = {
  "": [
    { name: "sermons", path: "sermons", type: "directory", size: null },
    { name: "sample-sermon.mp3", path: "sample-sermon.mp3", type: "file", size: 42_100_000 },
  ],
  sermons: [
    { name: "2026", path: "2026", type: "directory", size: null },
    { name: "old-sermon.mp3", path: "old-sermon.mp3", type: "file", size: 38_000_000 },
  ],
  "sermons/2026": [
    { name: "september.mp3", path: "september.mp3", type: "file", size: 51_200_000 },
  ],
};

const MOCK_DRIVE_TREE: Record<string, ApiCloudFile[]> = {
  "": [
    { name: "shared-sermon.mp3", path: "shared-sermon.mp3", type: "file", size: 47_500_000 },
  ],
};

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

function joinPath(base: string, rel: string): string {
  return base ? `${base.replace(/\/+$/, "")}/${rel}` : rel;
}

export function CloudBrowser({
  name,
  path,
  onPath,
  onUse,
  provider,
  attachedDriveId,
}: {
  name: string;
  path: string;
  onPath: (p: string) => void;
  onUse: (item: ApiCloudFile) => void;
  provider?: string;
  attachedDriveId?: string;
}) {
  const [drive, setDrive] = useState<ApiSharedDrive | null>(null);
  const driveId = drive?.id;
  const isDrive = provider === "drive";
  const sharedQuery = useQuery({
    queryKey: ["cloud", "shared-drives", name],
    queryFn: () =>
      isLive
        ? cloudApi.sharedDrives(name)
        : Promise.resolve({ items: MOCK_SHARED_DRIVES }),
    enabled: isDrive,
    staleTime: 30_000,
    retry: false,
  });
  const browse = useQuery({
    queryKey: ["cloud", "browse", name, path, driveId ?? ""],
    queryFn: () =>
      isLive
        ? cloudApi.browse(name, path, driveId)
        : Promise.resolve({ path, items: (driveId ? MOCK_DRIVE_TREE : MOCK_TREE)[path] ?? [] }),
    staleTime: 5_000,
  });
  const items = [...(browse.data?.items ?? [])].sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const segments = path ? path.split("/") : [];
  const parent = segments.slice(0, -1).join("/");
  const sharedDrives = sharedQuery.data?.items ?? [];
  const selectDrive = (next: ApiSharedDrive) => {
    setDrive((cur) => (cur?.id === next.id ? null : next));
    onPath("");
  };

  return (
    <div className="mt-3 rounded-lg border border-line bg-ink p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          Browsing <span className="font-mono text-accent">{name}</span>
          {drive ? <span className="text-muted"> (shared drive: {drive.name})</span> : null}
        </p>
        <div className="flex flex-wrap gap-2">
          {drive ? (
            <Button
              onClick={() => {
                setDrive(null);
                onPath("");
              }}
            >
              Back to My Drive
            </Button>
          ) : null}
          <Button onClick={() => onPath(parent)} disabled={!path}>
            Up one level
          </Button>
        </div>
      </div>
      <p className="mt-1 text-xs text-muted">
        Pick a file, then choose <span className="font-semibold text-mist">Use this file</span> to
        start a new sermon with it.
      </p>

      {isDrive ? (
        <details className="mt-2 rounded-md border border-line p-2">
          <summary className="cursor-pointer text-xs font-semibold text-muted">
            Shared with me
          </summary>
          {sharedQuery.isError ? (
            <p role="alert" className="mt-2 text-xs text-danger">
              {(sharedQuery.error as Error).message}
            </p>
          ) : sharedQuery.isPending ? (
            <p className="mt-2 text-xs text-muted" role="status">
              Loading shared drives…
            </p>
          ) : sharedDrives.length === 0 ? (
            <p className="mt-2 text-xs text-muted">No shared drives on this account.</p>
          ) : (
            <ul className="mt-2 flex flex-wrap gap-2">
              {sharedDrives.map((d) => {
                const active = drive?.id === d.id;
                const attached = attachedDriveId === d.id;
                return (
                  <li key={d.id}>
                    <button
                      type="button"
                      onClick={() => selectDrive(d)}
                      aria-pressed={active}
                      className={`rounded border px-2 py-1 text-left text-xs ${
                        active ? "border-accent text-mist" : "border-line text-muted hover:text-mist"
                      }`}
                    >
                      <span className="block font-semibold">{d.name}</span>
                      <span className="block font-mono text-[10px]">
                        {d.id}
                        {attached ? " · attached" : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted">
            Walk a shared drive here, then attach it from Cloud Mounts to use its files.
          </p>
        </details>
      ) : null}
      <nav aria-label="Folder path" className="mt-2 flex flex-wrap items-center gap-1 text-xs">
        <button
          type="button"
          onClick={() => onPath("")}
          className="rounded px-1 font-mono text-muted hover:text-mist"
        >
          root
        </button>
        {segments.map((seg, i) => (
          <span key={`${seg}-${i}`} className="flex items-center gap-1">
            <span aria-hidden="true" className="text-muted">
              /
            </span>
            <button
              type="button"
              onClick={() => onPath(segments.slice(0, i + 1).join("/"))}
              className="rounded px-1 font-mono text-muted hover:text-mist"
            >
              {seg}
            </button>
          </span>
        ))}
      </nav>

      {browse.isError ? (
        <p role="alert" className="mt-3 rounded-md border border-danger px-3 py-2 text-xs text-danger">
          {(browse.error as Error).message}
        </p>
      ) : browse.isPending ? (
        <p className="mt-3 text-xs text-muted" role="status">
          Loading folder…
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-xs text-muted">This folder is empty.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-line">
          {items.map((item) => {
            const full = joinPath(path, item.path);
            return (
              <li key={full} className="flex flex-wrap items-center gap-2 py-2">
                <Chip tone="neutral">{item.type === "directory" ? "folder" : "file"}</Chip>
                {item.type === "directory" ? (
                  <button
                    type="button"
                    onClick={() => onPath(full)}
                    className="min-w-0 flex-1 truncate rounded px-1 text-left text-sm hover:text-accent"
                  >
                    {item.name}
                  </button>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 truncate px-1 text-sm">{item.name}</span>
                    <span className="font-mono text-xs text-muted">{formatSize(item.size)}</span>
                    <Button variant="primary" onClick={() => onUse({ ...item, path: full })}>
                      Use this file
                    </Button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
