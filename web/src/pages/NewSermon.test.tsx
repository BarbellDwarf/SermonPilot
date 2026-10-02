import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewSermon } from "./NewSermon";
import { withProviders } from "../test/harness";

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
  return withProviders(<NewSermon />, entry);
}

async function fillMetadata(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Title (needed)"), "Sample Title");
  await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
  fireEvent.change(screen.getByLabelText("Date (needed)"), {
    target: { value: "2026-09-22" },
  });
}

const submitButton = () =>
  screen.getByRole("button", { name: "Start processing" }) as HTMLButtonElement;

const runSummary = () => screen.getByTestId("run-summary");
const runStatusBar = () => screen.getByTestId("run-status-bar");

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
    await user.upload(screen.getByLabelText("Choose a teaching file"), file);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(runSummary().textContent).toContain("sample-sermon.mp3");
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
    expect(runSummary().textContent).toContain("/media/sample-sermon.mp3");
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
    expect(runSummary().textContent).toContain("sample-remote");
    expect(runSummary().textContent).toContain("sample-sermon.mp3");
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
    expect(runStatusBar().textContent).toContain("Still needed: source file");

    await user.click(screen.getByRole("tab", { name: "Server path" }));
    expect(submitButton().disabled).toBe(true);
    expect(runStatusBar().textContent).toContain("Still needed: valid server path");

    await user.type(screen.getByRole("textbox", { name: "Server path" }), "/media/sample-sermon.mp3");
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.click(screen.getByRole("tab", { name: "Cloud file" }));
    expect(submitButton().disabled).toBe(true);
    expect(runStatusBar().textContent).toContain("Still needed: cloud file");

    await user.click(screen.getByRole("tab", { name: "Server path" }));
    await waitFor(() => expect(submitButton().disabled).toBe(false));

    await user.click(screen.getByRole("tab", { name: "Upload" }));
    expect(submitButton().disabled).toBe(true);
  });

  it("starts on the cloud option when a remote reference is prefilled", async () => {
    const user = userEvent.setup();
    const entry = `/new?server_path=${encodeURIComponent("remote:sample-remote:sermons/sample.mp3")}`;
    renderPage(entry);

    expect(screen.getByRole("tab", { name: "Cloud file" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    await fillMetadata(user);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    await user.click(submitButton());

    await waitFor(() => expect(mocks.createServerPath).toHaveBeenCalledTimes(1));
    expect(mocks.createServerPath.mock.calls[0][0]).toMatchObject({
      container_path: "remote:sample-remote:sermons/sample.mp3",
    });
  });
});

/**
 * Regression: the page used to render a developer debug strip along the
 * bottom, reading `upload:no file · untitled · no speaker · no date · enhance ·
 * transcribe · ai meta · live run · no edit · out:processed_sermons`. It
 * contradicted the toggles above it and leaked an internal output path.
 */
describe("no internal debug string reaches the operator", () => {
  const FORBIDDEN = [
    "upload:no file",
    "server:no path",
    "cloud:no file",
    "untitled",
    "no speaker",
    "no date",
    "no enhance",
    "no transcribe",
    "no ai meta",
    "ai meta",
    "live run",
    "no edit",
    "out:",
  ];

  it("leaks none of them on a blank form", () => {
    renderPage();
    const text = document.body.textContent ?? "";
    for (const token of FORBIDDEN) {
      expect(text.toLowerCase()).not.toContain(token);
    }
  });

  it("leaks none of them once the form is partly filled", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Title (needed)"), "Sample Title");
    await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
    fireEvent.change(screen.getByLabelText("Date (needed)"), { target: { value: "2026-09-22" } });
    const text = document.body.textContent ?? "";
    for (const token of FORBIDDEN) {
      expect(text.toLowerCase()).not.toContain(token);
    }
  });

  it("has no pipe-separated or middot-separated run of machine tokens", () => {
    renderPage();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/·\s*(no |out:|ai meta|live run)/);
    expect(text).not.toMatch(/\b(no enhance|no transcribe|no edit|no speaker|no date)\b/);
  });

  it("names the recording and the destination in plain words instead", async () => {
    const user = userEvent.setup();
    renderPage();
    await fillMetadata(user);
    const summary = runSummary();
    expect(summary.textContent).toContain("Recording");
    expect(summary.textContent).toContain("Files are saved to");
    expect(summary.textContent).toContain("the server's output folder");
    expect(summary.textContent).not.toMatch(/processed_sermons/);
  });
});

describe("the required path is short and says what is missing", () => {
  it("numbers only the two steps that are required", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "The recording" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "What it is" })).toBeTruthy();
    expect(screen.getByText("Processing options")).toBeTruthy();
    expect(screen.getByText("What happens when you start")).toBeTruthy();
  });

  it("collapses the pipeline toggles and summarises them in a sentence", () => {
    renderPage();
    const details = screen.getByText("Processing options").closest("details");
    expect(details).toBeTruthy();
    expect(details?.open).toBe(false);
    expect(details?.textContent).toContain("clean the audio");
    expect(details?.textContent).toContain("upload to SermonAudio at the end");
  });

  it("re-words the summary when a toggle changes", async () => {
    const user = userEvent.setup();
    renderPage();
    const details = screen.getByText("Processing options").closest("details") as HTMLDetailsElement;
    details.open = true;
    await user.click(screen.getByRole("switch", { name: "Dry run" }));
    expect(details.textContent).toContain("stop before uploading");
    expect(runSummary().textContent).toContain("Skip upload to sermonaudio");
  });

  it("lists every missing requirement in one place before submit", () => {
    renderPage();
    const text = runStatusBar().textContent ?? "";
    expect(text).toContain("Still needed");
    expect(text).toContain("source file");
    expect(text).toContain("title");
    expect(text).toContain("speaker");
    expect(text).toContain("date");
    expect(submitButton().disabled).toBe(true);
  });

  it("clears each requirement from the list as it is filled in", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(runStatusBar().textContent).toContain("source file, title, speaker, date");

    await user.type(screen.getByLabelText("Title (needed)"), "Sample Title");
    expect(runStatusBar().textContent).not.toContain("title");
    expect(runStatusBar().textContent).toContain("speaker");

    await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
    fireEvent.change(screen.getByLabelText("Date (needed)"), { target: { value: "2026-09-22" } });
    expect(runStatusBar().textContent).toContain("Still needed: source file");

    const file = new File(["audio"], "sample.mp3", { type: "audio/mpeg" });
    await user.upload(screen.getByLabelText("Choose a teaching file"), file);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(runStatusBar().textContent).not.toContain("Still needed");
  });
});

describe("validation appears inline as the operator works", () => {
  it("says nothing about a field nobody has touched yet", () => {
    renderPage();
    expect(screen.queryByText("Give the teaching a title.")).toBeNull();
    expect(screen.queryByText("Say who gave this.")).toBeNull();
    expect(screen.queryByText("Pick the day it was given.")).toBeNull();
    expect(screen.queryByText("Choose a file to upload.")).toBeNull();
  });

  it("complains under the title once it has been left empty", async () => {
    const user = userEvent.setup();
    renderPage();
    const title = screen.getByLabelText("Title (needed)");
    await user.click(title);
    await user.tab();
    expect(screen.getByText("Give the teaching a title.")).toBeTruthy();
    expect(title.getAttribute("aria-invalid")).toBe("true");
  });

  it("complains under the date once it has been left empty", async () => {
    const user = userEvent.setup();
    renderPage();
    const date = screen.getByLabelText("Date (needed)");
    await user.click(date);
    await user.tab();
    expect(screen.getByText("Pick the day it was given.")).toBeTruthy();
    expect(date.getAttribute("aria-invalid")).toBe("true");
  });

  it("stops complaining once the field is filled", async () => {
    const user = userEvent.setup();
    renderPage();
    const title = screen.getByLabelText("Title (needed)");
    await user.click(title);
    await user.tab();
    expect(screen.getByText("Give the teaching a title.")).toBeTruthy();
    await user.type(title, "Sample Title");
    await user.tab();
    expect(screen.queryByText("Give the teaching a title.")).toBeNull();
    expect(title.getAttribute("aria-invalid")).toBeNull();
  });

  it("only warns about a missing server path after the field has been visited", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("tab", { name: "Server path" }));
    expect(screen.queryByText("Enter an absolute path that exists on the server.")).toBeNull();
    await user.click(screen.getByRole("textbox", { name: "Server path" }));
    await user.tab();
    expect(screen.getByText("Enter an absolute path that exists on the server.")).toBeTruthy();
  });
});