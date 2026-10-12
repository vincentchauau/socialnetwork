import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Lets the app import ../../shared/frontend and keeps it in the standalone trace.
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(here, "../.."),
};

export default nextConfig;
