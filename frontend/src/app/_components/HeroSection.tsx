"use client";

import Link from "next/link";
import { motion, ease } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const TELEGRAM_BOT_URL = "https://t.me/hrbreaker_bot";

function TelegramIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={className}
      fill="currentColor"
    >
      <path d="M9.78 15.27 9.6 18.9c.4 0 .58-.18.79-.39l1.9-1.82 3.94 2.88c.72.4 1.24.19 1.43-.66l2.6-12.18c.25-1.1-.4-1.54-1.1-1.28L3.46 10.8c-1.07.42-1.06 1.02-.18 1.29l3.95 1.23 9.17-5.78c.43-.27.83-.12.5.18z" />
    </svg>
  );
}

export function HeroSection() {
  const { lang } = useLang();

  return (
    <section className="py-24 sm:py-32">
      <div className="mx-auto max-w-3xl text-center">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: ease.smooth }}
          className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl"
        >
          {t.hero.heading[lang]}
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: ease.smooth }}
          className="mt-6 text-lg text-muted-foreground sm:text-xl"
        >
          {t.hero.subheading[lang]}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: ease.smooth }}
          className="mt-10"
        >
          <Link href="/signin">
            <Button variant="accent" size="lg" className="text-base px-8">
              {t.hero.cta[lang]}
            </Button>
          </Link>
          <p className="mt-3 text-sm text-muted-foreground">
            {t.hero.ctaSub[lang]}
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3, ease: ease.smooth }}
          className="mt-8"
        >
          <a
            href={TELEGRAM_BOT_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Button variant="outline" size="lg" className="text-base px-8">
              <TelegramIcon className="text-[#229ED9]" />
              {t.hero.telegramCta[lang]}
            </Button>
          </a>
          <p className="mx-auto mt-3 max-w-xl text-sm text-muted-foreground">
            {t.hero.telegramCtaSub[lang]}
          </p>
        </motion.div>
      </div>
    </section>
  );
}
