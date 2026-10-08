import type { Metadata } from "next";
import { EnvironmentBanner } from "@/components/EnvironmentBanner";
import "@fontsource-variable/manrope";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/source-serif-4/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paperlight · 中文与英文学生写作工作台",
  description: "面向学生的中文与英文写作自检、作者审阅修改与版本工作台。公开本地体验无需上传文稿。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const connectPolicy = process.env.PAPERLIGHT_LOCAL_STAGING === "1"
    ? "'self' http://127.0.0.1:8100"
    : "'self' https: http://127.0.0.1:8000 http://localhost:8000";
  const scriptPolicy = process.env.NODE_ENV === "production"
    ? "script-src 'self' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";
  return (
    <html lang="zh-CN">
      <head>
        <meta
          httpEquiv="Content-Security-Policy"
          content={`default-src 'self'; ${scriptPolicy}; style-src 'self' 'unsafe-inline'; connect-src ${connectPolicy}; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'`}
        />
        <script src={`${basePath}/config.js`} defer />
      </head>
      <body><EnvironmentBanner enabled={process.env.PAPERLIGHT_LOCAL_STAGING === "1"} />{children}</body>
    </html>
  );
}
