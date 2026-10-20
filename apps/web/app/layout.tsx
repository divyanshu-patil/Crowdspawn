import type { Metadata } from "next";
import Link from "next/link";
import { Schibsted_Grotesk, Space_Mono } from "next/font/google";
import "./globals.css";
import { TileField } from "../components/TileField";
import { SfxListener, SoundToggle } from "../components/Sfx";
import { Tour } from "../components/Tour";
import { ServerStatus } from "../components/ServerStatus";

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
      {/* Browser extensions add attributes to <body>; don't let that read as a hydration bug. */}
      <body suppressHydrationWarning>
        <TileField />
        <SfxListener />
        <div className="shell">
          <nav className="nav" aria-label="Main">
            <Link href="/" className="brand">
              <span className="live-dot" aria-hidden />
              Crowdspawn
            </Link>
            <div className="nav-links">
              <SoundToggle />
              <Tour />
              <Link className="btn" href="/agent">
                Plan my launch
              </Link>
              <Link className="label" href="/sample">
                Sample
              </Link>
              <Link className="label" href="/scout">
                Explore map
              </Link>
            </div>
          </nav>
          <ServerStatus />
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
