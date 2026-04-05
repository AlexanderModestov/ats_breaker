"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { motion } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";
import { type Lang } from "../_lib/translations";

const languages: { code: Lang; label: string }[] = [
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
];

export function LandingHeader() {
  const { lang, setLang } = useLang();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const activeLang = languages.find((l) => l.code === lang)!;

  return (
    <motion.nav
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl"
    >
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <span className="text-sm font-bold text-primary-foreground">HR</span>
          </div>
          <span className="text-lg font-semibold tracking-tight">Breaker</span>
        </Link>

        <div className="flex items-center gap-3">
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setOpen(!open)}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            >
              {activeLang.label}
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
              >
                <path
                  d="M3 4.5L6 7.5L9 4.5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            {open && (
              <div className="absolute right-0 mt-1 min-w-[140px] rounded-lg border border-border bg-card shadow-lg py-1">
                {languages.map((l) => (
                  <button
                    key={l.code}
                    onClick={() => {
                      setLang(l.code);
                      setOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      l.code === lang
                        ? "font-medium text-foreground bg-secondary/60"
                        : "text-muted-foreground hover:text-foreground hover:bg-secondary/40"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="h-5 w-px bg-border" />

          <Link href="/signin">
            <Button variant="ghost" size="sm">
              {t.nav.login[lang]}
            </Button>
          </Link>
          <Link href="/signin">
            <Button variant="accent" size="sm">
              {t.nav.signup[lang]}
            </Button>
          </Link>
        </div>
      </div>
    </motion.nav>
  );
}
