import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
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
  getSetting: vi.fn(),
  putSetting: vi.fn(),
}));

vi.mock("../api/client", () => ({
  mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
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
  settingsApi: { get: mocks.getSetting, put: mocks.putSetting },
  serverPathApi: { stat: mocks.statPath, create: mocks.createServerPath },
  uploadApi: { upload: mocks.uploadFile },
  filesApi: { list: vi.fn(), explore: mocks.exploreFiles, downloadUrl: vi.fn(() => "") },
}));

function renderPage(entry = "/new") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/new", element: <NewSermon /> },
      { path: "/library", element: <p>Library page</p> },
    ],
    { initialEntries: [entry] },
  );
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, router };
}

async function fillMetadata(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Title (required)"), "Sample Title");
  await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
  fireEvent.change(screen.getByLabelText("Date (required)"), {
    target: { value: "2026-09-22" },
  });
}

const submitButton = () =>
  screen.getByRole("button", { name: "Start processing" }) as HTMLButtonElement;

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
  mocks.getSetting.mockResolvedValue({ key: "intake.defaults", value: null });
  mocks.putSetting.mockImplementation(async (key: string, value: unknown) => ({ key, value }));
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

  it("keeps dry run off by default and visible in processing options", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.queryByText("Advanced options")).toBeNull();
    const dryRun = screen.getByRole("switch", { name: "Dry run" });
    expect(dryRun.getAttribute("aria-checked")).toBe("false");

    await user.click(dryRun);
    expect(dryRun.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByLabelText("Selection summary").textContent).toContain("Dry run");
  });

  it("keeps a single primary action in the run summary", () => {
    renderPage();
    const summary = screen.getByLabelText("Selection summary");
    expect(within(summary).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Start processing",
    ]);
    expect(document.querySelectorAll("button.bg-accent")).toHaveLength(1);
    expect(within(summary).getByRole("status").textContent).toContain("Still needed:");
  });

  it("shows Source, Metadata, and Processing options as the three sections", () => {
    renderPage();
    expect(screen.getByRole("region", { name: "Source" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Metadata" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Processing options" })).toBeTruthy();
  });

  it("shows the event type default instead of a silent payload fallback", () => {
    renderPage();
    const eventType = screen.getByLabelText("Event type") as HTMLSelectElement;
    expect(eventType.value).toBe("Sunday Service");
    expect(screen.getByLabelText("Selection summary").textContent).toContain("Sunday Service");
  });

  it("derives the displayed file formats from the input accept value", () => {
    renderPage();
    const input = screen.getByLabelText("Choose a teaching file");
    const expected = (input.getAttribute("accept") ?? "")
      .split(",")
      .map((format) => format.trim().replace(/^\./, "").toUpperCase());
    const formats = within(screen.getByLabelText("Supported formats"))
      .getAllByText(/^[A-Z0-9]+$/)
      .map((chip) => chip.textContent);
    expect(formats).toEqual(expected);
  });

  it("shows a readable run summary with every current value", () => {
    renderPage();
    const summary = screen.getByLabelText("Selection summary");
    expect(summary.textContent).toContain("Upload · no file");
    expect(summary.textContent).toContain("Not set");
    expect(summary.textContent).toContain("Local · processed_sermons");
    expect(summary.textContent).toContain("Live upload");
    expect(summary.textContent).toContain("Audio enhancement");
    expect(summary.textContent).toContain("Transcription");
    expect(summary.textContent).toContain("Metadata generated");
  });

  it("saves per-run choices only when Save as my default is used", async () => {
    const user = userEvent.setup();
    renderPage();
    const destination = screen.getByLabelText("Destination") as HTMLSelectElement;
    await waitFor(() =>
      expect(destination.querySelector('option[value="cloud"]')?.hasAttribute("disabled")).toBe(false),
    );

    await user.selectOptions(destination, "cloud");
    expect(destination.value).toBe("cloud");
    await user.click(screen.getByRole("switch", { name: "Dry run" }));
    expect(mocks.putOutputDir).not.toHaveBeenCalled();
    expect(mocks.putSetting).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Save as my default" }));
    await waitFor(() => expect(mocks.putSetting).toHaveBeenCalledTimes(1));
    expect(mocks.putSetting.mock.calls[0][0]).toBe("intake.defaults");
    expect(mocks.putSetting.mock.calls[0][1]).toMatchObject({
      eventType: "Sunday Service",
      dryRun: true,
      enhance: true,
      transcribe: true,
      generateMetadata: true,
    });
    await waitFor(() => expect(mocks.putOutputDir).toHaveBeenCalledWith("remote:sample-remote:"));
  });

  it("loads saved per-run defaults from user settings", async () => {
    mocks.getSetting.mockResolvedValue({
      key: "intake.defaults",
      value: {
        eventType: "Bible Study",
        enhance: false,
        transcribe: true,
        generateMetadata: true,
        dryRun: true,
        autoEdit: false,
        autoEditMode: "interactive",
        logoPath: "none",
        fadeBlack: true,
      },
    });
    renderPage();

    await waitFor(() =>
      expect((screen.getByLabelText("Event type") as HTMLSelectElement).value).toBe("Bible Study"),
    );
    expect(screen.getByRole("switch", { name: "Dry run" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("switch", { name: "Enhance audio" }).getAttribute("aria-checked")).toBe("false");
  });

  it("paints no errors or invalid fields before interaction", () => {
    renderPage();

    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    expect(document.querySelectorAll("[aria-invalid]")).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toBe(
      "Still needed: source file, title, speaker, date.",
    );
    const start = submitButton();
    expect(start.disabled).toBe(true);
    expect(start.getAttribute("aria-describedby")).toBe("ns-readiness");
  });

  it("shows inline errors on blur and clears them once the field is filled", async () => {
    const user = userEvent.setup();
    renderPage();

    const title = screen.getByLabelText("Title (required)");
    await user.click(title);
    await user.tab();
    expect(screen.getByText("Add a title.")).toBeTruthy();
    expect(title.getAttribute("aria-invalid")).toBe("true");
    expect(title.getAttribute("aria-describedby")).toBe("ns-title-error");
    await user.type(title, "Sample Title");
    expect(screen.queryByText("Add a title.")).toBeNull();
    expect(title.hasAttribute("aria-invalid")).toBe(false);

    const speaker = screen.getByRole("combobox", { name: "Speaker" });
    await user.click(speaker);
    await user.tab();
    expect(screen.getByText("Add a speaker.")).toBeTruthy();
    expect(speaker.getAttribute("aria-invalid")).toBe("true");
    expect(speaker.getAttribute("aria-describedby")).toBe("ns-speaker-error");

    const date = screen.getByLabelText("Date (required)");
    await user.click(date);
    await user.tab();
    expect(screen.getByText("Add the recording date.")).toBeTruthy();
    expect(date.getAttribute("aria-invalid")).toBe("true");
    expect(date.getAttribute("aria-describedby")).toBe("ns-date-error");
  });

  it("focuses the first invalid source after a submit attempt", async () => {
    renderPage();
    fireEvent.submit(document.querySelector("form") as HTMLFormElement);

    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Choose file" })),
    );
    expect(screen.getByText("Choose a file to upload.")).toBeTruthy();
    expect(screen.getByText("Add a title.")).toBeTruthy();
    expect(screen.getByText("Add a speaker.")).toBeTruthy();
    expect(screen.getByText("Add the recording date.")).toBeTruthy();
  });

  it("shows the source error only after the source is touched", () => {
    renderPage();
    const fileInput = screen.getByLabelText("Choose a teaching file");

    expect(screen.queryByText("Choose a file to upload.")).toBeNull();
    fireEvent.blur(fileInput);
    expect(screen.getByText("Choose a file to upload.")).toBeTruthy();
    expect(fileInput.getAttribute("aria-invalid")).toBe("true");
    expect(fileInput.getAttribute("aria-describedby")).toBe("ns-source-error");
  });

  it("uses one dropzone control with no nested interactive role", () => {
    renderPage();
    const panel = document.getElementById("source-panel-browser") as HTMLElement;
    const button = within(panel).getByRole("button", { name: "Choose file" });

    expect(panel.getAttribute("role")).toBeNull();
    expect(panel.querySelector('[role="button"]')).toBeNull();
    expect(button.parentElement?.getAttribute("role")).toBeNull();
    expect(button.className).toContain("bg-raised");
    expect(button.className).not.toContain("bg-accent");

    const fileInput = screen.getByLabelText("Choose a teaching file");
    expect(fileInput.tabIndex).toBe(-1);
    expect(button.contains(fileInput)).toBe(false);
  });

  it("keeps reset in the header overflow menu", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "Reset form" })).toBeTruthy();
  });

  it("guards client navigation and unload until Stay or Discard is chosen", async () => {
    const user = userEvent.setup();
    const { router } = renderPage();
    await user.type(screen.getByLabelText("Title (required)"), "Draft title");

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    await act(async () => {
      await router.navigate("/library");
    });
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stay" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/new");

    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/new");

    await act(async () => {
      await router.navigate("/library");
    });
    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/library"));
    expect(screen.getByText("Library page")).toBeTruthy();
  });

  it("clears the navigation guard when the form is reset", async () => {
    const user = userEvent.setup();
    const { router } = renderPage();
    await user.type(screen.getByLabelText("Title (required)"), "Draft title");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Reset form" }));
    await user.click(screen.getByRole("button", { name: "Reset form" }));

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);

    await act(async () => {
      await router.navigate("/library");
    });
    expect(router.state.location.pathname).toBe("/library");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("queues a browser upload carrying the file", async () => {
    const user = userEvent.setup();
    const { router } = renderPage();
    await fillMetadata(user);

    const file = new File(["audio-bytes"], "sample-sermon.mp3", { type: "audio/mpeg" });
    await user.upload(screen.getByLabelText("Choose a teaching file"), file);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(screen.getByLabelText("Selection summary").textContent).toContain(
      "Upload · sample-sermon.mp3",
    );
    await user.click(submitButton());

    await waitFor(() => expect(mocks.uploadFile).toHaveBeenCalledTimes(1));
    const form = mocks.uploadFile.mock.calls[0][0] as FormData;
    expect(form.get("file")).toBe(file);
    expect(form.get("title")).toBe("Sample Title");
    expect(form.get("speaker")).toBe("Sample Speaker");
    expect(form.get("event_type")).toBe("Sunday Service");
    expect(mocks.createServerPath).not.toHaveBeenCalled();

    await act(async () => {
      await router.navigate("/library");
    });
    expect(router.state.location.pathname).toBe("/library");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("queues a server path as container_path", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.selectOptions(screen.getByRole("combobox", { name: "Source" }), "server");
    await user.type(screen.getByRole("textbox", { name: "Server path" }), "/media/sample-sermon.mp3");
    await fillMetadata(user);
    await waitFor(() => expect(submitButton().disabled).toBe(false));
    expect(screen.getByLabelText("Selection summary").textContent).toContain(
      "Server path · /media/sample-sermon.mp3",
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
      "Cloud · sample-remote/sample-sermon.mp3",
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
    fireEvent.blur(screen.getByLabelText("Choose a teaching file"));
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
