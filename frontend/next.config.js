/** @type {import('next').NextConfig} */

// The browser always calls same-origin /api/*; Next.js forwards it to the backend.
// No CORS, no API URL baked into the client, works from any device on the network.
// BACKEND_URL is read at build time: http://backend:8000 in Docker, localhost in dev.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Minimal self-contained build so the Docker runtime image doesn't need node_modules.
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

module.exports = nextConfig;
