import type { Metadata } from "next";
import Link from "next/link";
import { Schibsted_Grotesk, Space_Mono } from "next/font/google";
import "./globals.css";

const display = Schibsted_Grotesk({ subsets: ["latin"], weight: ["500"], variable: "--font-schibsted" });
const mono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-space-mono" });

export const metadata: Metadata = {
  title: "Crowdspawn: find where your players already are",
  description:
    "Launch planning for indie games: the cities where fans of comparable games over-index, and the artists, podcasts, films and brands they love. Built on Qloo taste data.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>
        <div className="shell">
          <nav className="nav" aria-label="Main">
            <Link href="/" className="brand">
              <span className="live-dot" aria-hidden />
              Crowdspawn
            </Link>
            <div className="nav-links">
              <Link className="label" href="/sample">
                Sample
              </Link>
              <Link className="btn" href="/plan/new">
                New plan
              </Link>
            </div>
          </nav>
          <main id="main">{children}</main>
          <footer className="foot spread">
            <span className="label muted">Data: Qloo Taste AI · Affinity index, not a sales forecast</span>
            <span className="label muted">Built for the Qloo Agentic Hackathon 2026</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
