import withSerwistInit from "@serwist/next";

// next.config 不保证已加载 .env 文件，这里显式读取本地 .env.local（缺省或
// Node < 20.12 时优雅降级为 loopback-only）。经反代域名做本地开发时在
// frontend/.env.local 设置 OOPSNOTE_DEV_ALLOWED_ORIGIN。
try {
  process.loadEnvFile(new URL("./.env.local", import.meta.url));
} catch {
  // 没有 .env.local 或运行时不支持 loadEnvFile：仅允许 loopback。
}
const extraDevOrigin = process.env.OOPSNOTE_DEV_ALLOWED_ORIGIN;

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
  allowedDevOrigins: ['127.0.0.1', 'localhost', ...(extraDevOrigin ? [extraDevOrigin] : [])],
  // Enable standalone output for production deployment
  output: 'standalone',
  serverExternalPackages: ['better-sqlite3'],
  async rewrites() {
    // This is evaluated by Next.js on the server/build side. Keep the Docker
    // service hostname out of browser-visible NEXT_PUBLIC_* configuration.
    const backendUrl = process.env.OOPSNOTE_BACKEND_URL || 'http://127.0.0.1:8000';

    // Let filesystem route handlers own /api/auth and /api/backend first.
    // The legacy rewrite remains only for the pre-cutover frontend callers.
    return {
      afterFiles: [
        {
          source: '/api/:path((?!auth(?:/|$)|backend(?:/|$)).*)',
          destination: `${backendUrl}/:path*`,
        },
      ],
    };
  },
  async redirects() {
    return [{ source: '/settings/providers', destination: '/settings/channels', permanent: false }];
  },
};

export default withSerwist(nextConfig);
