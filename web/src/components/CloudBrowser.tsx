import { useQuery } from "@tanstack/react-query";
import { cloudApi, isLive, type ApiCloudFile, type ApiCloudRemote } from "../api/client";
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
}: {
  name: string;
  path: string;
  onPath: (p: string) => void;
  onUse: (item: ApiCloudFile) => void;
}) {
  const browse = useQuery({
    queryKey: ["cloud", "browse", name, path],
    queryFn: () =>
      isLive
        ? cloudApi.browse(name, path)
        : Promise.resolve({ path, items: MOCK_TREE[path] ?? [] }),
    staleTime: 5_000,
  });
  const items = [...(browse.data?.items ?? [])].sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const segments = path ? path.split("/") : [];
  const parent = segments.slice(0, -1).join("/");

  return (
    <div className="mt-3 rounded-lg border border-line bg-ink p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          Browsing <span className="font-mono text-accent">{name}</span>
        </p>
        <Button onClick={() => onPath(parent)} disabled={!path}>
          Up one level
        </Button>
      </div>
      <p className="mt-1 text-xs text-muted">
        Pick a file, then choose <span className="font-semibold text-mist">Use this file</span> to
        start a new sermon with it.
      </p>
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
