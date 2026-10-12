import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The gateway serves this app under /chat.
  basePath: "/chat",
  output: "standalone",
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(here, "../.."),
};

export default nextConfig;
