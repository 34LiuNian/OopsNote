import withSerwistInit from "@serwist/next";

const withSerwist = withSerwistInit({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV === "development",
  register: true,
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || '.next',
  allowedDevOrigins: ['127.0.0.1', 'localhost', 'dev-oopsnote.alan-ztr.eu.org'],
  // Enable standalone output for production deployment
  output: 'standalone',
  async rewrites() {
    // This is evaluated by Next.js on the server/build side. Keep the Docker
    // service hostname out of browser-visible NEXT_PUBLIC_* configuration.
    const backendUrl = process.env.OOPSNOTE_BACKEND_URL || 'http://127.0.0.1:8000';
    
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default withSerwist(nextConfig);
