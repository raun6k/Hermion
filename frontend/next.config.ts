import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal Docker image; only the Dockerfile sets this (plain `next start` cannot serve standalone).
  output: process.env.NEXT_STANDALONE === "true" ? "standalone" : undefined,
  distDir: process.env.NEXT_DIST_DIR ?? ".next", // e2e builds separately from `pnpm dev`
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
