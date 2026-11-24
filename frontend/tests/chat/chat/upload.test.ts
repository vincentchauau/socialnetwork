import { apiFetch, apiForm } from "@sn/api";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { isServicePath, runUpload } from "../../../app/chat/upload";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), apiForm: vi.fn() }));
const json = vi.mocked(apiFetch);
const form = vi.mocked(apiForm);

beforeEach(() => {
  json.mockReset();
  form.mockReset();
});

describe("the calls a form makes before it is sent to the chat", () => {
  it("sends the file and the text of a photo, and keeps the id of what was made", async () => {
    form.mockResolvedValue({ id: 5 } as never);
    const file = new File(["x"], "a.png", { type: "image/png" });
    const kept = await runUpload(
      { steps: [{ path: "/api/file/upload", kind: "multipart", fields: ["file", "caption"], capture: { photo_id: "id" } }], send: ["photo_id"] },
      { file, caption: "Sunset" },
    );
    expect(kept).toEqual({ photo_id: 5 });
    const sent = form.mock.calls[0][1] as FormData;
    expect(form.mock.calls[0][0]).toBe("/api/file/upload");
    expect(sent.get("file")).toBeInstanceOf(File);
    expect(sent.get("caption")).toBe("Sunset");
  });

  it("makes the item first and then sends its picture with the id it got", async () => {
    json.mockResolvedValue({ id: 9 } as never);
    form.mockResolvedValue({} as never);
    const file = new File(["x"], "a.png");
    const kept = await runUpload(
      {
        steps: [
          { path: "/api/art/items", kind: "json", fields: ["kind", "title", "categories"], capture: { item_id: "id" } },
          { path: "/api/art/files", kind: "multipart", fields: ["file"], extra: ["item_id"], capture: {} },
        ],
        send: ["item_id"],
      },
      { kind: "gallery", title: "Roses", categories: ["red"], file },
    );
    expect(kept).toEqual({ item_id: 9 });
    expect(JSON.parse(String(json.mock.calls[0][1]?.body))).toEqual({ kind: "gallery", title: "Roses", categories: ["red"] });
    const second = form.mock.calls[0][1] as FormData;
    expect(second.get("item_id")).toBe("9");
    expect(second.get("file")).toBeInstanceOf(File);
    expect(second.get("title")).toBeNull();
  });

  it("sends a true/false as text, a list as repeated fields, and leaves out what is empty", async () => {
    form.mockResolvedValue({ id: 1 } as never);
    await runUpload(
      { steps: [{ path: "/api/watch/videos", kind: "multipart", fields: ["title", "tags", "rights_confirmed", "description"], capture: { video_id: "id" } }], send: ["video_id"] },
      { title: "Cat", tags: ["a", "b"], rights_confirmed: true, description: "" },
    );
    const sent = form.mock.calls[0][1] as FormData;
    expect(sent.getAll("tags")).toEqual(["a", "b"]);
    expect(sent.get("rights_confirmed")).toBe("true");
    expect(sent.has("description")).toBe(false);
  });

  it("stops at the first call that fails, with what the service said", async () => {
    json.mockResolvedValue({ id: 9 } as never);
    form.mockRejectedValue(new Error("Photo limit reached"));
    await expect(
      runUpload(
        { steps: [{ path: "/api/art/items", kind: "json", fields: [], capture: { item_id: "id" } }, { path: "/api/art/files", kind: "multipart", fields: ["file"], capture: {} }], send: ["item_id"] },
        {},
      ),
    ).rejects.toThrow("Photo limit reached");
  });

  it("only calls paths of the gateway for a service", async () => {
    for (const bad of ["https://evil.example/x", "//evil.example/x", "/api/../etc", "/other/photos", "/api/", "/api/a b"]) {
      expect(isServicePath(bad), bad).toBe(false);
      await expect(runUpload({ steps: [{ path: bad, kind: "json", fields: [], capture: {} }], send: [] }, {})).rejects.toThrow();
    }
    expect(isServicePath("/api/file/upload")).toBe(true);
    expect(json).not.toHaveBeenCalled();
  });
});
