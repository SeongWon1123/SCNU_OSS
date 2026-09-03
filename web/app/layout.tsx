import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '리포닥 — RepoDoc',
  description:
    'GitHub 공개 저장소 URL 하나로 보안·라이선스·한국 규제 준수를 진단하는 오픈소스 클리닉',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="dark">
      <body className="bg-neutral-950 font-sans text-neutral-100 antialiased">
        {children}
      </body>
    </html>
  );
}
