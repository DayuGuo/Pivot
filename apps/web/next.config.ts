import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  ...(process.env.PIVOT_STANDALONE === "true" ? {output: "standalone" as const, outputFileTracingRoot: path.resolve(__dirname, "../..")} : {}),
  async headers() {
    return [{source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "same-origin"},
      {key: "X-Frame-Options", value: "DENY"},
      {key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()"},
    ]}];
  },
};
export default nextConfig;
