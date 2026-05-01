import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8082";

const nextConfig: NextConfig = {
  // trailing slash 308リダイレクトを無効化:
  // /api/v1/jobs/ → 308 → /api/v1/jobs → 307(FastAPI) → localhost:8082 の連鎖を断ち切る
  skipTrailingSlashRedirect: true,
  async rewrites() {

    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_ORIGIN}/api/v1/:path*`,
      },
      {
        source: "/outputs/:path*",
        destination: `${API_ORIGIN}/outputs/:path*`,
      },
      {
        source: "/static/:path*",
        destination: `${API_ORIGIN}/static/:path*`,
      },
      {
        source: "/health",
        destination: `${API_ORIGIN}/health`,
      },
    ];
  },
  // 大きなMP4をNext.jsのbody sizeリミットで詰まらせないためのプロキシ設定
  experimental: {
    proxyTimeout: 600000, // 10分
  },
};

export default nextConfig;

