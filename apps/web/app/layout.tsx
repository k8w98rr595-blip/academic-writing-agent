import type { Metadata } from "next";
import "@fontsource-variable/manrope";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/source-serif-4/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paperlight — Academic Writing Agent",
  description: "Owner-controlled academic writing review and revision workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const scriptPolicy = process.env.NODE_ENV === "production"
    ? "script-src 'self' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";
  return (
    <html lang="zh-CN">
      <head>
        <meta
          httpEquiv="Content-Security-Policy"
          content={`default-src 'self'; ${scriptPolicy}; style-src 'self' 'unsafe-inline'; connect-src 'self' https: http://127.0.0.1:8000 http://localhost:8000; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'`}
        />
        <script src={`${basePath}/config.js`} defer />
      </head>
      <body>{children}</body>
    </html>
  );
}
