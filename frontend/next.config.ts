import type { NextConfig } from "next";

// The browser talks to /api on the same origin; Next proxies it to FastAPI.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default config;
