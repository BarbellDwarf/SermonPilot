import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewSermon } from "./NewSermon";

const mocks = vi.hoisted(() => ({
  listBranding: vi.fn(),
  uploadBranding: vi.fn(),
  listCloud: vi.fn(),
  browseCloud: vi.fn(),
  sharedDrives: vi.fn(),
  facets: vi.fn(),
  getOutputDir: vi.fn(),
  putOutputDir: vi.fn(),
  statPath: vi.fn(),
  createServerPath: vi.fn(),
  uploadFile: vi.fn(),
  exploreFiles: vi.fn(),
}));

vi.mock("../api/client", () => ({
  isLive: true,
  brandingApi: { list: mocks.listBranding, upload: mocks.uploadBranding },
  cloudApi: {
    list: mocks.listCloud,
    browse: mocks.browseCloud,
    sharedDrives: mocks.sharedDrives,
    providers: vi.fn(),
    oauthApps: vi.fn(),
    setOAuthApp: vi.fn(),
    authUrl: vi.fn(),
    authorizePaste: vi.fn(),
    oauthStart: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
    attachSharedDrive: vi.fn(),
    detachSharedDrive: vi.fn(),
  },
  libraryApi: { facets: mocks.facets },
  outputDirApi: { get: mocks.getOutputDir, put: mocks.putOutputDir },
  serverPathApi: { stat: mocks.statPath, create: mocks.createServerPath },
  uploadApi: { upload: mocks.uploadFile },
  filesApi: { list: vi.fn(), explore: mocks.exploreFiles, downloadUrl: vi.fn(() => "") },
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/new"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <NewSermon />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function fillMetadata(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Title (required)"), "Sample Title");
  await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
  fireEvent.change(screen.getByLabelText("Date (required)"), {
    target: { value: "2026-09-22" },
  });
}

const submitButton = () =>
  screen.getByRole("button", { name: "Start Processing" }) as HTMLButtonElement;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listBranding.mockResolvedValue({ items: [] });
  mocks.listCloud.mockResolvedValue({
    items: [{ name: "sample-remote", provider: "drive", status: "configured" }],
    total: 1,
  });
  mocks.browseCloud.mockResolvedValue({
    path: "",
    items: [
      {
        name: "sermons",
        path: "sermons",
        type: "directory",
        size: null,
        modified: "2026-09-20T20:47:00",
      },
      {
        name: "sample-sermon.mp3",
        path: "sample-sermon.mp3",
        type: "file",
        size: 42_100_000,
        modified: "2026-09-20T20:47:00",
      },
    ],
  });
  mocks.sharedDrives.mockResolvedValue({ items: [] });
  mocks.facets.mockResolvedValue({ speakers: [], series: [], event_types: [] });
  mocks.getOutputDir.mockResolvedValue({ output_dir: "processed_sermons", source: "default" });
  mocks.statPath.mockResolvedValue({
    exists: true,
    is_file: true,
    size: 42_100_000,
    size_human: "42.1 MB",
    ext: "mp3",
    kind: "audio",
    name: "sample-sermon.mp3",
  });
  mocks.createServerPath.mockResolvedValue({
    id: "s-1",
    job_id: "job-1",
    status: "queued",
    filename: "sample-sermon.mp3",
    size: 42_100_000,
    size_human: "42.1 MB",
    ext: "mp3",
    kind: "audio",
  });
  mocks.uploadFile.mockResolvedValue({
    id: "s-1",
    job_id: "job-upload",
    status: "queued",
    filename: "sample-sermon.mp3",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("NewSermon source options", () => {
  it("renders three peer options and marks exactly one selected at a time", async () => {
    const user = userEvent.setup();
    renderPage();

    const upload = screen.getByRole("tab", { name: "Upload" });
    const server = screen.getByRole("tab", { name: "Server path" });
    const cloud = screen.getByRole("tab", { name: "Cloud file" });
    expect(upload).toBeTruthy();
    expect(server).toBeTruthy();
    expect(cloud).toBeTruthy();
    expect(upload.getAttribute("aria-selected")).toBe("true");

    await user.click(server);
    expect(server.getAttribute("aria-selected")).toBe("true");
    expect(upload.getAttribute("aria-selected")).toBe("false");
    expect(cloud.getAttribute("aria-selected")).toBe("false");

    await user.click(cloud);
    expect(cloud.getAttribute("aria-selected")).toBe("true");
    expect(server.getAttribute("aria-selected")).toBe("false");
  });

  it("queues a browser upload carrying the file", async () => {
    const user = userEvent.setup();
    renderPage();
    await fillMetadata(user);

    const file = new File(["audio-bytes"], "sample-sermon.mp3", { type: "audio/mpeg" });
    await user.upload(screen.getByLabelText("Choose a sermon file"), file);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(screen.getByLabelText("Selection summary").textContent).toContain(
      "upload:sample-sermon.mp3",
    );
    await user.click(submitButton());

    await waitFor(() => expect(mocks.uploadFile).toHaveBeenCalledTimes(1));
    const form = mocks.uploadFile.mock.calls[0][0] as FormData;
    expect(form.get("file")).toBe(file);
    expect(form.get("title")).toBe("Sample Title");
    expect(form.get("speaker")).toBe("Sample Speaker");
    expect(mocks.createServerPath).not.toHaveBeenCalled();
  });

  it("queues a server path as container_path", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("tab", { name: "Server path" }));
    await user.type(screen.getByRole("textbox", { name: "Server path" }), "/media/sample-sermon.mp3");
    await fillMetadata(user);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(screen.getByLabelText("Selection summary").textContent).toContain(
      "server:/media/sample-sermon.mp3",
    );
    await user.click(submitButton());

    await waitFor(() => expect(mocks.createServerPath).toHaveBeenCalledTimes(1));
    expect(mocks.createServerPath.mock.calls[0][0]).toMatchObject({
      container_path: "/media/sample-sermon.mp3",
    });
    expect(mocks.uploadFile).not.toHaveBeenCalled();
  });

  it("queues a cloud file as a remote reference", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(mocks.listCloud).toHaveBeenCalled());
    await user.click(screen.getByRole("tab", { name: "Cloud file" }));
    await user.selectOptions(screen.getByLabelText("Cloud remote"), "sample-remote");

    const useButton = await screen.findByRole("button", { name: "Use this file" });
    await user.click(useButton);
    await fillMetadata(user);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(screen.getByLabelText("Selection summary").textContent).toContain(
      "cloud:remote:sample-remote:sample-sermon.mp3",
    );
    await user.click(submitButton());

    await waitFor(() => expect(mocks.createServerPath).toHaveBeenCalledTimes(1));
    expect(mocks.createServerPath.mock.calls[0][0]).toMatchObject({
      container_path: "remote:sample-remote:sample-sermon.mp3",
    });
    expect(mocks.uploadFile).not.toHaveBeenCalled();
  });

  it("keeps submit disabled until the selected option has a source, and re-evaluates on switch", async () => {
    const user = userEvent.setup();
    renderPage();
    await fillMetadata(user);

    expect(submitButton().disabled).toBe(true);
    expect(screen.getByText("Choose a file to upload.")).toBeTruthy();

    await user.click(screen.getByRole("tab", { name: "Server path" }));
    expect(submitButton().disabled).toBe(true);
    expect(screen.getByText("Enter an absolute path that exists on the server.")).toBeTruthy();

    await user.type(screen.getByRole("textbox", { name: "Server path" }), "/media/sample-sermon.mp3");
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.click(screen.getByRole("tab", { name: "Cloud file" }));
    expect(submitButton().disabled).toBe(true);
    expect(screen.getByText(/Pick a file with/)).toBeTruthy();

    await user.click(screen.getByRole("tab", { name: "Server path" }));
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.click(screen.getByRole("tab", { name: "Upload" }));
    expect(submitButton().disabled).toBe(true);
  });
});
