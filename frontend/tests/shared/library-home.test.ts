import { describe, expect, it } from "vitest";

import { isLibraryHome, libraryEntryOf } from "../../app/chat/dock/libraries";

describe("library home", () => {
  it("matches the home path, with or without a trailing slash, and nothing under it", () => {
    expect(isLibraryHome("/video", "/video")).toBe(true);
    expect(isLibraryHome("/video/", "/video")).toBe(true);
    expect(isLibraryHome("/video/abc", "/video")).toBe(false);
  });

  it("knows the home of each library app and none for the others", () => {
    expect(libraryEntryOf("face")?.home).toBe("/face");
    expect(libraryEntryOf("chat")).toBeUndefined();
  });
});
