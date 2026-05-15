"use client";

import Link from "next/link";
import { motion, fadeSlideUp } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function PainSection() {
  const { lang } = useLang();

  return (
    <section className="py-20">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeSlideUp}
          className="rounded-2xl border border-border/50 bg-card p-8 sm:p-10 space-y-6"
        >
          <h2 className="text-2xl font-bold sm:text-3xl">
            {t.pain.heading[lang]}
          </h2>

          <div className="space-y-3 text-muted-foreground">
            <p>{t.pain.intro[lang]}</p>
            <ul className="space-y-2 pl-1">
              {t.pain.items.map((item, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  {item[lang]}
                </li>
              ))}
            </ul>
          </div>

          <p className="font-semibold text-foreground">{t.pain.slogan[lang]}</p>

          <Link href="/signin">
            <Button size="lg" className="w-full sm:w-auto px-8">
              {t.pain.cta[lang]}
            </Button>
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
