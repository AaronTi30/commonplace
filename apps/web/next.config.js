import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname, "../.."),
  // Hide the Next.js dev indicator ("N" badge) in the corner during `next dev`.
  devIndicators: false
};

export default nextConfig;

