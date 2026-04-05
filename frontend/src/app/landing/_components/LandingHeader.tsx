"use client";

import Link from "next/link";
import { motion } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingHeader() {
  const { lang, setLang } = useLang();

  return (
    <motion.nav
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl"
    >
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/landing" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <span className="text-sm font-bold text-primary-foreground">HR</span>
          </div>
          <span className="text-lg font-semibold tracking-tight">Breaker</span>
        </Link>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setLang(lang === "en" ? "ru" : "en")}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {lang === "en" ? "RU" : "EN"}
          </button>

          <div className="h-5 w-px bg-border" />

          <Link href="/login">
            <Button variant="ghost" size="sm">
              {t.nav.login[lang]}
            </Button>
          </Link>
          <Link href="/login">
            <Button variant="accent" size="sm">
              {t.nav.signup[lang]}
            </Button>
          </Link>
        </div>
      </div>
    </motion.nav>
  );
}
