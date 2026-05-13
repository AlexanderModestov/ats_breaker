"use client";

import { ShieldCheck, Target, Eye, FileText } from "lucide-react";
import { motion, fadeSlideUp } from "@/components/motion";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const icons = [ShieldCheck, Target, Eye, FileText];

export function FeaturesSection() {
  const { lang } = useLang();

  return (
    <section className="py-20">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center text-3xl font-bold">
          {t.features.heading[lang]}
        </h2>

        <div className="mt-12 grid gap-8 sm:grid-cols-2">
          {t.features.items.map((item, i) => {
            const Icon = icons[i];
            return (
              <motion.div
                key={i}
                initial="initial"
                whileInView="animate"
                viewport={{ once: true, margin: "-50px" }}
                variants={fadeSlideUp}
                className="flex gap-4"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10">
                  <Icon className="h-5 w-5 text-accent" />
                </div>
                <p className="text-sm text-muted-foreground">
                  {item.description[lang]}
                </p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
