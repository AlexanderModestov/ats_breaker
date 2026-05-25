"use client";

import Link from "next/link";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingFooter() {
  const { lang } = useLang();

  return (
    <footer className="bg-zinc-950">
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-10 sm:flex-row sm:justify-between">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-700">
                <span className="text-sm font-bold text-white">HR</span>
              </div>
              <span className="text-lg font-semibold tracking-tight text-white">
                Breaker
              </span>
            </div>
            <p className="mt-3 text-sm text-zinc-400">{t.footer.tagline[lang]}</p>
          </div>

          {/* Links */}
          <div className="flex gap-12">
            <div>
              <h3 className="text-sm font-semibold text-zinc-400">{t.footer.links[lang]}</h3>
              <ul className="mt-3 space-y-2">
                <li>
                  <a href="#pricing" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">
                    {t.footer.pricing[lang]}
                  </a>
                </li>
                <li>
                  <Link href="/signin" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">
                    {t.footer.login[lang]}
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-400">{t.footer.legal[lang]}</h3>
              <ul className="mt-3 space-y-2">
                <li><span className="text-sm text-zinc-500">{t.footer.privacy[lang]}</span></li>
                <li><span className="text-sm text-zinc-500">{t.footer.terms[lang]}</span></li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-10 border-t border-zinc-800 pt-6">
          <p className="text-center text-xs text-zinc-600">{t.footer.copyright[lang]}</p>
        </div>
      </div>
    </footer>
  );
}
