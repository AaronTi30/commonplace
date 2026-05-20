import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname, "../.."),
  // Hide the Next.js dev indicator ("N" badge) in the corner during `next dev`.
  devIndicators: false,
  // epubjs "module" field points at untranspiled src/; use the compiled lib build.
  transpilePackages: ["epubjs"],
  turbopack: {
    resolveAlias: {
      epubjs: path.resolve(__dirname, "node_modules/epubjs/lib/index.js"),
    },
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      epubjs: path.resolve(__dirname, "node_modules/epubjs/lib/index.js"),
    };
    return config;
  },
};

export default nextConfig;

