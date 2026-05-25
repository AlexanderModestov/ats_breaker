import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import Script from "next/script";
import "./globals.css";
import { Providers } from "./providers";
import { JsonLd } from "./components/JsonLd";

export const metadata: Metadata = {
  metadataBase: new URL("https://hrbreaker.co"),
  title: {
    default: "HR-Breaker — ATS Resume Optimization for Any Job Posting",
    template: "%s | HR-Breaker",
  },
  description:
    "HR-Breaker optimizes your resume to match any job posting, runs an ATS simulation, and returns a tailored PDF in seconds. Free to try — no credit card required.",
  applicationName: "HR-Breaker",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    url: "https://hrbreaker.co/",
    siteName: "HR-Breaker",
    title: "HR-Breaker — ATS Resume Optimization for Any Job Posting",
    description:
      "Optimize your resume for any job posting. Pass ATS filters with confidence — no fabrications, no hallucinations.",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "HR-Breaker — ATS Resume Optimization for Any Job Posting",
    description:
      "Optimize your resume for any job posting. Pass ATS filters with confidence.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <Script
          src="https://telegram.org/js/telegram-web-app.js"
          strategy="beforeInteractive"
        />
      </head>
      <body className={`${GeistSans.variable} font-sans antialiased`} suppressHydrationWarning>
        <JsonLd />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
