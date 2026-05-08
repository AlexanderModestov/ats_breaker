"use client";

import Link from "next/link";
import { Sparkles, Compass, Target } from "lucide-react";
import { motion, fadeSlideUp, staggerContainer, staggerItem } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const icons = [Sparkles, Compass, Target];

export function AICoachSection() {
  const { lang } = useLang();

  return (
    <section className="py-20">
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-100px" }}
          variants={fadeSlideUp}
          className="text-center"
        >
          <h2 className="text-3xl font-bold">{t.aiCoach.heading[lang]}</h2>
          <p className="mt-4 text-lg text-muted-foreground">
            {t.aiCoach.intro[lang]}
          </p>
        </motion.div>

        <p className="mt-10 text-center text-base font-medium">
          {t.aiCoach.feedbackHeading[lang]}
        </p>

        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={staggerContainer}
          className="mt-6 grid gap-4 sm:grid-cols-3"
        >
          {t.aiCoach.feedbackItems.map((item, i) => {
            const Icon = icons[i];
            return (
              <motion.div key={i} variants={staggerItem}>
                <Card className="h-full text-center">
                  <CardContent className="pt-6">
                    <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-accent/10">
                      <Icon className="h-5 w-5 text-accent" />
                    </div>
                    <h3 className="mt-3 text-base font-semibold">
                      {item.title[lang]}
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {item.description[lang]}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </motion.div>

        <motion.p
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeSlideUp}
          className="mt-10 text-center text-lg text-muted-foreground"
        >
          {t.aiCoach.outro[lang]}
        </motion.p>

        <div className="mt-10 flex justify-center">
          <Link href="/signin">
            <Button variant="accent" size="lg" className="text-base px-8">
              {t.aiCoach.cta[lang]}
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}
