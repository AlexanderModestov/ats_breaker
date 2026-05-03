"use client";

import { FileUp, Link as LinkIcon, Download, MessagesSquare } from "lucide-react";
import { motion, staggerContainer, staggerItem } from "@/components/motion";
import { Card, CardContent } from "@/components/ui/card";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const icons = [FileUp, LinkIcon, Download, MessagesSquare];

export function HowItWorksSection() {
  const { lang } = useLang();

  return (
    <section className="py-20 bg-secondary/30">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center text-3xl font-bold">
          {t.howItWorks.heading[lang]}
        </h2>

        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
        >
          {t.howItWorks.steps.map((step, i) => {
            const Icon = icons[i];
            return (
              <motion.div key={i} variants={staggerItem}>
                <Card className="h-full text-center">
                  <CardContent className="pt-6">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
                      <Icon className="h-6 w-6 text-accent" />
                    </div>
                    <div className="mt-2 text-sm font-medium text-muted-foreground">
                      {i + 1}
                    </div>
                    <h3 className="mt-2 text-lg font-semibold">
                      {step.title[lang]}
                    </h3>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {step.description[lang]}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
