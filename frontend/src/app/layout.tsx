import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "COCORO Studio | AI インフルエンサー動画生成",
  description: "企業専属AIインフルエンサー動画自動生成システム - COCORO Influencer Studio",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
