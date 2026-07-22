import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) for a small
  // production Docker image that runs with `node server.js`.
  output: "standalone",
};

export default nextConfig;
