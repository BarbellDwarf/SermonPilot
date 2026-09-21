import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MediaPlayer } from "./MediaPlayer";

describe("MediaPlayer", () => {
  it("shows the honest empty state when the artifact is unavailable", () => {
    render(
      <MediaPlayer
        sermonId="s-1"
        kind="processed"
        available={false}
        emptyMessage="Not rendered yet."
      />,
    );
    expect(screen.getByTestId("media-empty")).toBeTruthy();
    expect(screen.getByText("Not rendered yet.")).toBeTruthy();
    expect(document.querySelector("video")).toBeNull();
    expect(document.querySelector("audio")).toBeNull();
  });

  it("renders a video element sourced from the processed artifact", () => {
    render(
      <MediaPlayer sermonId="s-1" kind="processed" contentType="video/mp4" available />,
    );
    const element = document.querySelector("video[data-media-kind='processed']");
    expect(element).toBeTruthy();
    expect(element?.getAttribute("src")).toBe("/api/media/sermons/s-1/processed");
    expect(element?.hasAttribute("controls")).toBe(true);
    expect(document.querySelector("audio")).toBeNull();
  });

  it("renders an audio element for an audio content type", () => {
    render(<MediaPlayer sermonId="s-2" kind="enhanced" contentType="audio/mpeg" available />);
    const element = document.querySelector("audio[data-media-kind='enhanced']");
    expect(element).toBeTruthy();
    expect(element?.getAttribute("src")).toBe("/api/media/sermons/s-2/enhanced");
    expect(document.querySelector("video")).toBeNull();
  });

  it("treats keeper and snippets as video without a content type", () => {
    render(<MediaPlayer sermonId="s-3" kind="keeper" available />);
    expect(document.querySelector("video[data-media-kind='keeper']")).toBeTruthy();
    render(<MediaPlayer sermonId="s-3" kind="snippet_start" available />);
    expect(document.querySelector("video[data-media-kind='snippet_start']")).toBeTruthy();
  });

  it("falls back to Preview unavailable when the element errors", () => {
    render(
      <MediaPlayer sermonId="s-1" kind="processed" contentType="video/mp4" available />,
    );
    const element = document.querySelector("video");
    expect(element).toBeTruthy();
    fireEvent.error(element as HTMLVideoElement);
    expect(screen.getByText("Preview unavailable.")).toBeTruthy();
    expect(document.querySelector("video")).toBeNull();
  });

  it("renders a marker jump button per cut", () => {
    render(
      <MediaPlayer
        sermonId="s-1"
        kind="source"
        contentType="audio/mpeg"
        available
        markers={[
          { atSec: 12.5, label: "Start" },
          { atSec: 95, label: "End" },
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: /Start · 00:12\.5/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /End · 01:35\.0/ })).toBeTruthy();
  });
});
