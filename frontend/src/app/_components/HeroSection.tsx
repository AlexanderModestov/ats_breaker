"use client";

import Link from "next/link";
import { motion, ease } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

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
      </div>
    </section>
  );
}
