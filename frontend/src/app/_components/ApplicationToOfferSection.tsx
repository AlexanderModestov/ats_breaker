"use client";

import Link from "next/link";
import { FileCheck2, MessagesSquare } from "lucide-react";
import { motion, staggerContainer, staggerItem } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const icons = [FileCheck2, MessagesSquare];

export function ApplicationToOfferSection() {
  const { lang } = useLang();

  return (
    <section className="py-20">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center text-3xl font-bold">
          {t.applicationToOffer.heading[lang]}
        </h2>
        <p className="mt-4 text-center text-lg text-muted-foreground">
          {t.applicationToOffer.subheading[lang]}
        </p>

        <motion.div
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="mt-12 grid gap-6 sm:grid-cols-2"
        >
          {t.applicationToOffer.cards.map((card, i) => {
            const Icon = icons[i];
            return (
              <motion.div key={i} variants={staggerItem}>
                <Card className="h-full">
                  <CardContent className="pt-6">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
                      <Icon className="h-6 w-6 text-accent" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold">
                      {card.title[lang]}
                    </h3>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {card.description[lang]}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </motion.div>

        <div className="mt-10 text-center">
          <Link href="/signin">
            <Button variant="accent" size="lg" className="text-base px-8">
              {t.applicationToOffer.cta[lang]}
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}
