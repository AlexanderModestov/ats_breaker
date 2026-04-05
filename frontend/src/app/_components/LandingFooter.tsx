"use client";

import Link from "next/link";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingFooter() {
  const { lang } = useLang();

  return (
    <footer className="border-t border-border/50 bg-secondary/50">
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 sm:grid-cols-3">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <span className="text-sm font-bold text-primary-foreground">HR</span>
              </div>
              <span className="text-lg font-semibold tracking-tight">Breaker</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {t.footer.tagline[lang]}
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-sm font-semibold">{t.footer.links[lang]}</h3>
            <ul className="mt-3 space-y-2">
              <li>
                <a href="#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  {t.footer.pricing[lang]}
                </a>
              </li>
              <li>
                <Link href="/signin" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  {t.footer.login[lang]}
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="text-sm font-semibold">{t.footer.legal[lang]}</h3>
            <ul className="mt-3 space-y-2">
              <li>
                <span className="text-sm text-muted-foreground">
                  {t.footer.privacy[lang]}
                </span>
              </li>
              <li>
                <span className="text-sm text-muted-foreground">
                  {t.footer.terms[lang]}
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border/50 pt-6">
          <p className="text-center text-xs text-muted-foreground">
            {t.footer.copyright[lang]}
          </p>
        </div>
      </div>
    </footer>
  );
}
