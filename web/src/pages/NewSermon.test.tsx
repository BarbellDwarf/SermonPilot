import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

function renderPage(entry = "/new") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[entry]}
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
  it("exposes one source select and shows only the picker for the chosen source", async () => {
    const user = userEvent.setup();
    renderPage();

    const source = screen.getByRole("combobox", { name: "Source" }) as HTMLSelectElement;
    expect(Array.from(source.options).map((o) => o.textContent)).toEqual([
      "Upload",
      "Server path",
      "Cloud file",
    ]);
    expect(source.value).toBe("browser");
    expect(document.getElementById("source-panel-browser")).toBeTruthy();
    expect(document.getElementById("source-panel-server")).toBeNull();
    expect(document.getElementById("source-panel-cloud")).toBeNull();

    await user.selectOptions(source, "server");
    expect(document.getElementById("source-panel-server")).toBeTruthy();
    expect(document.getElementById("source-panel-browser")).toBeNull();

    await user.selectOptions(source, "cloud");
    expect(document.getElementById("source-panel-cloud")).toBeTruthy();
    expect(document.getElementById("source-panel-server")).toBeNull();
  });

  it("keeps dry run off by default and hides it inside the advanced disclosure", async () => {
    const user = userEvent.setup();
    renderPage();

    const details = screen.getByText("Advanced options").closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
    const dryRun = screen.getByRole("switch", { name: "Dry run" });
    expect(dryRun.getAttribute("aria-checked")).toBe("false");

    await user.click(screen.getByText("Advanced options"));
    expect(screen.getByRole("switch", { name: "Dry run" }).getAttribute("aria-checked")).toBe("false");
    await user.click(dryRun);
    expect(dryRun.getAttribute("aria-checked")).toBe("true");
  });

  it("keeps a single primary action in the footer bar", () => {
    renderPage();
    const footer = screen.getByLabelText("Selection summary");
    expect(within(footer).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Start Processing",
    ]);
    expect(within(footer).getByRole("status").textContent).toContain("Missing:");
  });

  it("keeps reset in the header overflow menu", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "Reset form" })).toBeTruthy();
  });

  it("queues a browser upload carrying the file", async () => {
    const user = userEvent.setup();
    renderPage();
    await fillMetadata(user);

    const file = new File(["audio-bytes"], "sample-sermon.mp3", { type: "audio/mpeg" });
    await user.upload(screen.getByLabelText("Choose a teaching file"), file);
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
    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "server");
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
    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "cloud");
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

    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "server");
    expect(submitButton().disabled).toBe(true);
    expect(screen.getByText("Enter an absolute path that exists on the server.")).toBeTruthy();

    await user.type(screen.getByRole("textbox", { name: "Server path" }), "/media/sample-sermon.mp3");
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "cloud");
    expect(submitButton().disabled).toBe(true);
    expect(screen.getByText(/Pick a file with/)).toBeTruthy();

    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "server");
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "browser");
    expect(submitButton().disabled).toBe(true);
  });

  it("starts on the cloud option when a remote reference is prefilled", async () => {
    const user = userEvent.setup();
    const entry = `/new?server_path=${encodeURIComponent("remote:sample-remote:sermons/sample.mp3")}`;
    renderPage(entry);

    expect((screen.getByRole("combobox", { name: "Source" }) as HTMLSelectElement).value).toBe("cloud");
    await fillMetadata(user);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    await user.click(submitButton());

    await waitFor(() => expect(mocks.createServerPath).toHaveBeenCalledTimes(1));
    expect(mocks.createServerPath.mock.calls[0][0]).toMatchObject({
      container_path: "remote:sample-remote:sermons/sample.mp3",
    });
  });

  it("sends the generate-metadata-on-upload choice with the submission", async () => {
    const user = userEvent.setup();
    renderPage();
    await fillMetadata(user);

    const toggle = screen.getByRole("switch", { name: "Generate metadata on upload" });
    expect(toggle.getAttribute("aria-checked")).toBe("true");

    await user.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    const file = new File(["audio-bytes"], "sample-sermon.mp3", { type: "audio/mpeg" });
    await user.upload(screen.getByLabelText("Choose a teaching file"), file);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    await user.click(submitButton());

    await waitFor(() => expect(mocks.uploadFile).toHaveBeenCalledTimes(1));
    const form = mocks.uploadFile.mock.calls[0][0] as FormData;
    expect(form.get("skip_ai_generation")).toBe("true");
  });
});
