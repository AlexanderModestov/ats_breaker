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
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true }}
          variants={fadeSlideUp}
          className="text-center"
        >
          <h2 className="text-3xl font-bold">{t.pricing.heading[lang]}</h2>
          <p className="mt-3 text-muted-foreground text-lg">
            {t.pricing.subtitle[lang]}
          </p>
        </motion.div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {t.pricing.plans.map((plan, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.1 }}
              className={`relative rounded-2xl border p-8 flex flex-col ${
                plan.highlighted
                  ? "border-foreground bg-card shadow-lg ring-1 ring-foreground/10"
                  : "border-border bg-card"
              }`}
            >
              {plan.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-foreground px-4 py-1 text-xs font-semibold text-background">
                  {lang === "en" ? "Most Popular" : "Популярный"}
                </div>
              )}

              <div>
                <h3 className="text-lg font-semibold">{plan.name[lang]}</h3>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-4xl font-bold tracking-tight">
                    €{plan.price}
                  </span>
                  {plan.price !== "0" && (
                    <span className="text-muted-foreground text-sm">
                      {t.pricing.monthly[lang]}
                    </span>
                  )}
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  {plan.description[lang]}
                </p>
              </div>

              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map((feature, j) => (
                  <li key={j} className="flex items-start gap-2.5 text-sm">
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      className="mt-0.5 shrink-0 text-foreground"
                    >
                      <path
                        d="M4 8.5L6.5 11L12 5"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    {feature[lang]}
                  </li>
                ))}
              </ul>

              <div className="mt-8">
                <Link href="/login" className="block">
                  <Button
                    variant={plan.highlighted ? "accent" : "outline"}
                    size="lg"
                    className="w-full"
                  >
                    {plan.cta[lang]}
                  </Button>
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
