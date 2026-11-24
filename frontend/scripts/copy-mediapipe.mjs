// Copies the MediaPipe FaceMesh runtime (js, wasm, data, binarypb) from node_modules into
// public/mediapipe so the browser never loads it from a CDN. Runs on postinstall and prebuild.
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(root, "node_modules", "@mediapipe", "face_mesh");
const dest = path.join(root, "public", "mediapipe");
const RUNTIME = /\.(js|wasm|data|binarypb)$/;

if (!existsSync(src)) {
  console.error(`@mediapipe/face_mesh not found at ${src}; run npm install first.`);
  process.exit(1);
}
mkdirSync(dest, { recursive: true });
for (const file of readdirSync(src).filter((f) => RUNTIME.test(f))) {
  cpSync(path.join(src, file), path.join(dest, file));
}
