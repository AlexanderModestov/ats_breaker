"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { motion, fadeSlideUp } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function PricingSection() {
  const { lang } = useLang();

  return (
    <section id="pricing" className="py-20 bg-white scroll-mt-16">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true }}
          variants={fadeSlideUp}
        >
          <div className="mx-auto max-w-4xl text-center">
            <p className="text-xs font-semibold uppercase tracking-widest text-violet-600">Pricing</p>
            <h2 className="mt-2 text-4xl font-bold tracking-tight text-zinc-900">
              Simple, transparent pricing.
            </h2>
            <p className="mt-3 text-zinc-500">Start free. Upgrade when you&apos;re ready.</p>
          </div>
        </motion.div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {t.pricing.plans.map((plan, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.1 }}
              className={
                plan.highlighted
                  ? "rounded-lg border border-violet-400 bg-violet-50 p-8 flex flex-col"
                  : "rounded-lg border border-zinc-200 bg-white p-8 flex flex-col"
              }
            >
              <div>
                <h3 className="text-lg font-semibold">{plan.name[lang]}</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {plan.tagline[lang]}
                </p>
              </div>

              <div className="mt-3">
                <div className="text-4xl font-bold text-zinc-900">{plan.price[lang]}</div>
                {plan.priceSuffix[lang] && (
                  <p className="mt-1 text-sm text-zinc-400">{plan.priceSuffix[lang]}</p>
                )}
              </div>

              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map((feature, j) => (
                  <li key={j} className="flex items-start gap-2.5 text-sm">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400" />
                    <span>{feature[lang]}</span>
                    {"soon" in feature && feature.soon && (
                      <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide leading-none text-red-600 dark:text-red-400">
                        soon
                      </span>
                    )}
                  </li>
                ))}
              </ul>

              <div className="mt-6 pt-6 border-t border-zinc-200">
                <Link href="/signin">
                  {plan.highlighted ? (
                    <Button className="w-full bg-violet-700 hover:bg-violet-800 text-white">
                      {lang === "en" ? "Start Free" : "Начать бесплатно"}
                    </Button>
                  ) : (
                    <Button variant="outline" className="w-full">
                      {lang === "en" ? "Get Started" : "Начать"}
                    </Button>
                  )}
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
