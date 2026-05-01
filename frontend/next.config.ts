import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8082";

const nextConfig: NextConfig = {
  // Next.js App Router のリダイレクト動作制御
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      // --- API: スラッシュなし → FastAPIへスラッシュ付きでプロキシ
      {
        source: "/api/v1/:path*/",
        destination: `${API_ORIGIN}/api/v1/:path*/`,
      },
      {
        source: "/api/v1/:path*",
        destination: `${API_ORIGIN}/api/v1/:path*/`,
      },
      // --- 静的ファイル
      {
        source: "/outputs/:path*",
        destination: `${API_ORIGIN}/outputs/:path*`,
      },
      {
        source: "/static/:path*",
        destination: `${API_ORIGIN}/static/:path*`,
      },
      // --- ヘルスチェック
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

