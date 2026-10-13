import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Win = Window & { FaceMesh?: unknown };

class FakeMesh {
  static last: FakeMesh | null = null;
  static emit: "result" | "none" | "never" = "result";
  static initFails = false;
  static sendFails = false;
  static hang = false;
  listener: ((r: unknown) => void) | null = null;
  options: unknown = null;
  closed = false;
  constructor(public config: { locateFile: (f: string) => string }) {
    FakeMesh.last = this;
  }
  setOptions(o: unknown) { this.options = o; }
  onResults(l: (r: unknown) => void) { this.listener = l; }
  async initialize() { if (FakeMesh.initFails) throw new Error("wasm"); }
  async send() {
    if (FakeMesh.sendFails) throw new Error("send");
    if (FakeMesh.hang) await new Promise<void>(() => undefined);
    if (FakeMesh.emit === "result") this.listener?.({ multiFaceLandmarks: [[{ x: 0.1, y: 0.2 }]] });
    if (FakeMesh.emit === "none") this.listener?.({});
  }
  async close() { this.closed = true; }
}

const loadModule = async () => {
  vi.resetModules();
  return import("../app/lib/mediapipe");
};

beforeEach(() => {
  delete (window as Win).FaceMesh;
  FakeMesh.last = null;
  FakeMesh.emit = "result";
  FakeMesh.initFails = false;
  FakeMesh.sendFails = false;
  FakeMesh.hang = false;
  document.head.innerHTML = "";
  // jsdom has no WebGL: pretend the browser can create a context unless a test says otherwise
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as never);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("loadFaceMeshScript", () => {
  it("reuses window.FaceMesh when already present", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const mod = await loadModule();
    await expect(mod.loadFaceMeshScript()).resolves.toBe(FakeMesh);
    expect(document.head.querySelector("script")).toBeNull();
  });

  it("injects the self-hosted script once and resolves on load", async () => {
    const mod = await loadModule();
    const first = mod.loadFaceMeshScript();
    const second = mod.loadFaceMeshScript();
    const scripts = document.head.querySelectorAll("script");
    expect(scripts).toHaveLength(1);
    expect(scripts[0].getAttribute("src")).toBe("/face/mediapipe/face_mesh.js");
    (window as Win).FaceMesh = FakeMesh;
    scripts[0].onload?.(new Event("load"));
    await expect(first).resolves.toBe(FakeMesh);
    await expect(second).resolves.toBe(FakeMesh);
  });

  it("rejects with ModelLoadError on a network error and allows a retry", async () => {
    const mod = await loadModule();
    const failed = mod.loadFaceMeshScript();
    document.head.querySelector("script")!.onerror?.(new Event("error"));
    await expect(failed).rejects.toMatchObject({ name: "ModelLoadError" });
    const retry = mod.loadFaceMeshScript();
    expect(document.head.querySelectorAll("script")).toHaveLength(2);
    (window as Win).FaceMesh = FakeMesh;
    document.head.querySelectorAll("script")[1].onload?.(new Event("load"));
    await expect(retry).resolves.toBe(FakeMesh);
  });

  it("rejects when the script loads but defines nothing", async () => {
    const mod = await loadModule();
    const p = mod.loadFaceMeshScript();
    document.head.querySelector("script")!.onload?.(new Event("load"));
    await expect(p).rejects.toMatchObject({ name: "ModelLoadError" });
  });
});

describe("createMediaPipeLandmarker", () => {
  const video = document.createElement("video");

  it("self-hosts assets and returns landmarks for a frame", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const mod = await loadModule();
    const landmarker = await mod.createMediaPipeLandmarker();
    expect(FakeMesh.last!.config.locateFile("face_mesh.wasm")).toBe("/face/mediapipe/face_mesh.wasm");
    expect(FakeMesh.last!.options).toMatchObject({ maxNumFaces: 1 });
    await expect(landmarker.detect(video)).resolves.toEqual([{ x: 0.1, y: 0.2 }]);
    landmarker.close();
    expect(FakeMesh.last!.closed).toBe(true);
  });

  it("returns null when no face is found or no result callback fires", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const landmarker = await (await loadModule()).createMediaPipeLandmarker();
    FakeMesh.emit = "none";
    await expect(landmarker.detect(video)).resolves.toBeNull();
    FakeMesh.emit = "never";
    await expect(landmarker.detect(video)).resolves.toBeNull();
  });

  it("propagates send failures", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const landmarker = await (await loadModule()).createMediaPipeLandmarker();
    FakeMesh.sendFails = true;
    await expect(landmarker.detect(video)).rejects.toThrow("send");
  });

  it("wraps initialisation failures in ModelLoadError", async () => {
    (window as Win).FaceMesh = FakeMesh;
    FakeMesh.initFails = true;
    await expect((await loadModule()).createMediaPipeLandmarker()).rejects.toMatchObject({ name: "ModelLoadError" });
  });
});

describe("WebGL handling", () => {
  const video = document.createElement("video");
  it("hasWebGL is true with webgl2, true with webgl only, false without, and false when getContext throws", async () => {
    const mod = await loadModule();
    const spy = vi.spyOn(HTMLCanvasElement.prototype, "getContext");
    spy.mockImplementation(((kind: string) => (kind === "webgl2" ? {} : null)) as never);
    expect(mod.hasWebGL()).toBe(true);
    spy.mockImplementation(((kind: string) => (kind === "webgl" ? {} : null)) as never);
    expect(mod.hasWebGL()).toBe(true);
    spy.mockReturnValue(null);
    expect(mod.hasWebGL()).toBe(false);
    spy.mockImplementation((() => {
      throw new Error("blocked");
    }) as never);
    expect(mod.hasWebGL()).toBe(false);
  });

  it("refuses to load the model without WebGL, before touching the script", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    await expect((await loadModule()).createMediaPipeLandmarker()).rejects.toMatchObject({ name: "WebglUnavailableError" });
    expect(document.head.querySelector("script")).toBeNull();
  });

  it("turns MediaPipe's native WebGL alert into a rejected detect() and restores alert on close", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const nativeAlert = vi.fn();
    window.alert = nativeAlert;
    const landmarker = await (await loadModule()).createMediaPipeLandmarker();
    expect(window.alert).not.toBe(nativeAlert);
    FakeMesh.hang = true;
    const pending = landmarker.detect(video);
    window.alert("Failed to create WebGL canvas context when passing video frame.");
    await expect(pending).rejects.toMatchObject({ name: "WebglUnavailableError" });
    expect(nativeAlert).not.toHaveBeenCalled();
    window.alert("something else");
    expect(nativeAlert).toHaveBeenCalledWith("something else");
    landmarker.close();
    expect(window.alert).toBe(nativeAlert);
  });

  it("ignores a WebGL alert when no detection is pending and restores alert if initialisation fails", async () => {
    (window as Win).FaceMesh = FakeMesh;
    const nativeAlert = vi.fn();
    window.alert = nativeAlert;
    const landmarker = await (await loadModule()).createMediaPipeLandmarker();
    expect(() => window.alert("WebGL context lost")).not.toThrow();
    landmarker.close();
    FakeMesh.initFails = true;
    await expect((await loadModule()).createMediaPipeLandmarker()).rejects.toMatchObject({ name: "ModelLoadError" });
    expect(window.alert).toBe(nativeAlert);
  });
});

describe("openUserCamera", () => {
  it("rejects with UnsupportedError without mediaDevices", async () => {
    vi.stubGlobal("navigator", {});
    await expect((await loadModule()).openUserCamera()).rejects.toMatchObject({ name: "UnsupportedError" });
  });

  it("requests a front video-only stream", async () => {
    const stream = {} as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    await expect((await loadModule()).openUserCamera()).resolves.toBe(stream);
    expect(getUserMedia).toHaveBeenCalledWith(expect.objectContaining({ audio: false, video: expect.objectContaining({ facingMode: "user" }) }));
  });
});
