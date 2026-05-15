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
      <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeSlideUp}
          className="text-center"
        >
          <h2 className="text-3xl font-bold">{t.pain.heading[lang]}</h2>
          <p className="mt-4 text-lg text-muted-foreground">{t.pain.intro[lang]}</p>
        </motion.div>

        <motion.ul
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeSlideUp}
          className="mt-8 space-y-3 text-muted-foreground"
        >
          {t.pain.items.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span className="text-base">{item[lang]}</span>
            </li>
          ))}
        </motion.ul>

        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeSlideUp}
          className="mt-8 text-center"
        >
          <p className="text-lg font-semibold">{t.pain.slogan[lang]}</p>
          <div className="mt-6">
            <Link href="/signin">
              <Button size="lg" className="px-8">
                {t.pain.cta[lang]}
              </Button>
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
