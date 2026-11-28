import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LibrarySermon } from "../../mock/data";
import { DetailsForm } from "./DetailsForm";

const sermon: LibrarySermon = {
  id: "s-1",
  title: "A teaching",
  speaker: "Speaker A",
  date: "2026-09-06",
  duration: "42:10",
  series: "Sample Series",
  status: "rendered",
};

describe("DetailsForm", () => {
  it("keeps every field open and saves through a secondary action", async () => {
    const user = userEvent.setup();
    const onSaveDetails = vi.fn().mockResolvedValue(undefined);
    render(
      <DetailsForm
        sermon={sermon}
        description="A description."
        hashtags="#faith"
        isLive
        onSaveDetails={onSaveDetails}
        onToast={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Title")).toBeVisible();
    expect(screen.getByLabelText("Speaker")).toBeVisible();
    expect(screen.queryByText("Edit title and speaker")).toBeNull();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Renamed teaching");
    await user.click(screen.getByRole("button", { name: "Save details" }));

    expect(onSaveDetails).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Renamed teaching", speaker: "Speaker A" }),
    );
    expect(screen.getByRole("button", { name: "Save details" }).className).toContain("bg-raised");
  });

  it("renders read-only details with a send-back action", async () => {
    const user = userEvent.setup();
    const onSendBack = vi.fn();
    render(
      <DetailsForm
        sermon={sermon}
        description="A description."
        hashtags="#faith"
        isLive={false}
        readOnly
        onSendBack={onSendBack}
        onToast={vi.fn()}
      />,
    );

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("Speaker A")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Send back with note" }));
    expect(onSendBack).toHaveBeenCalledTimes(1);
  });
});
