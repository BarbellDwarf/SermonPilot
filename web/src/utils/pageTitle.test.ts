import { describe, expect, it } from "vitest";
import { pageTitle } from "./pageTitle";

describe("pageTitle", () => {
  it.each([
    ["/", "Inbox · SermonPilot"],
    ["/new", "New teaching · SermonPilot"],
    ["/library", "Library · SermonPilot"],
    ["/library/", "Library · SermonPilot"],
    ["/library/s-01", "Teaching review · SermonPilot"],
    ["/teaching/s-01", "Teaching review · SermonPilot"],
    ["/activity", "Activity · SermonPilot"],
    ["/activity/job-1", "Activity · SermonPilot"],
    ["/settings", "Settings · SermonPilot"],
    ["/settings/preferences", "Settings · SermonPilot"],
    ["/missing", "Not found · SermonPilot"],
  ])("titles %s as %s", (path, title) => {
    expect(pageTitle(path)).toBe(title);
  });
});
