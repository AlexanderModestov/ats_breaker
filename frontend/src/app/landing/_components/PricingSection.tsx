"use client";

import Link from "next/link";
import { motion, fadeSlideUp } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function PricingSection() {
  const { lang } = useLang();

  return (
    <section className="py-20 bg-secondary/30">
      <motion.div
        initial="initial"
        whileInView="animate"
        viewport={{ once: true }}
        variants={fadeSlideUp}
        className="mx-auto max-w-5xl px-4 text-center sm:px-6 lg:px-8"
      >
        <h2 className="text-3xl font-bold">{t.pricing.heading[lang]}</h2>
        <div className="mt-8">
          <Link href="/pricing">
            <Button variant="accent" size="lg">
              {t.pricing.cta[lang]}
            </Button>
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
