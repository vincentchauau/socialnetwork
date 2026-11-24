import { describe, expect, it } from "vitest";

import { libraryOf } from "../../app/chat/dock/libraries";

describe("libraryOf", () => {
  it("has the library of each app and none for chat or unknown apps", () => {
    for (const api of ["face"]) expect(libraryOf(api)).toBeDefined();
    expect(libraryOf("chat")).toBeUndefined();
    expect(libraryOf("toString")).toBeUndefined();
    expect(libraryOf("nope")).toBeUndefined();
  });
});
