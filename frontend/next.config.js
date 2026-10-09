/** @type {import('next').NextConfig} */

// The browser always calls same-origin /api/*; Next.js forwards it to the backend.
// No CORS, no API URL baked into the client, works from any device on the network.
// BACKEND_URL (or NEXT_PUBLIC_API_URL) is read at build time: set it on Render to the backend's
// address; it is http://backend:8000 in Docker and localhost in development.
const BACKEND_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig = {
  // Reading a scan with the model can take longer than the proxy's default 30 seconds;
  // without this the browser gets "Request failed (500)" while the backend is still working.
  experimental: { proxyTimeout: 120000 },
  // Minimal self-contained build so the Docker runtime image doesn't need node_modules.
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

module.exports = nextConfig;
