# Landing Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a bilingual (EN/RU) landing page at `/landing` that promotes HR-Breaker and drives users to sign up.

**Architecture:** Single Next.js page at `app/landing/page.tsx` with its own layout (no app Navbar). Language state managed via React context. All content stored in a single translations object. Reuses existing UI components (Button, Card) and motion helpers.

**Tech Stack:** Next.js App Router, Tailwind CSS, Framer Motion, Lucide React icons, existing UI component library.

**Design doc:** `docs/plans/2026-04-05-landing-page-design.md`

---

### Task 1: Translation Context

**Files:**
- Create: `frontend/src/app/landing/_lib/translations.ts`
- Create: `frontend/src/app/landing/_lib/LangContext.tsx`

**Step 1: Create translations file**

```typescript
// frontend/src/app/landing/_lib/translations.ts

export type Lang = "en" | "ru";

export const t = {
  nav: {
    login: { en: "Log In", ru: "Войти" },
    signup: { en: "Sign Up", ru: "Регистрация" },
  },
  hero: {
    heading: {
      en: "Stop getting filtered out. Start getting interviews.",
      ru: "Хватит терять отклики. Начните получать собеседования.",
    },
    subheading: {
      en: "Optimize your resume for any job posting. Pass ATS filters with confidence.",
      ru: "Адаптируйте резюме под любую вакансию. Пройдите ATS-фильтры уверенно.",
    },
    cta: { en: "Get Started", ru: "Начать" },
    ctaSub: {
      en: "Free to try. No credit card required.",
      ru: "Попробуйте бесплатно. Карта не нужна.",
    },
  },
  howItWorks: {
    heading: { en: "How It Works", ru: "Как это работает" },
    steps: [
      {
        title: { en: "Upload Your Resume", ru: "Загрузите резюме" },
        description: {
          en: "Paste or upload your resume in any format — PDF, LaTeX, plain text.",
          ru: "Вставьте или загрузите резюме в любом формате — PDF, LaTeX, текст.",
        },
      },
      {
        title: { en: "Add a Job Posting", ru: "Добавьте вакансию" },
        description: {
          en: "Paste a job URL or description. We extract the key requirements automatically.",
          ru: "Вставьте ссылку или описание. Мы автоматически извлечём ключевые требования.",
        },
      },
      {
        title: { en: "Get Your Optimized Resume", ru: "Получите оптимизированное резюме" },
        description: {
          en: "Receive a tailored, ATS-ready PDF resume in seconds.",
          ru: "Получите адаптированное PDF-резюме, готовое к ATS, за секунды.",
        },
      },
    ],
  },
  features: {
    heading: { en: "Why HR-Breaker", ru: "Почему HR-Breaker" },
    items: [
      {
        title: { en: "ATS-Optimized", ru: "Оптимизация под ATS" },
        description: {
          en: "Your resume is tested against real ATS simulation before you get it.",
          ru: "Резюме проверяется симуляцией ATS перед выдачей.",
        },
      },
      {
        title: { en: "Keyword Matching", ru: "Подбор ключевых слов" },
        description: {
          en: "We analyze the job posting and ensure your resume hits the right keywords.",
          ru: "Анализируем вакансию и обеспечиваем попадание по ключевым словам.",
        },
      },
      {
        title: { en: "No Fabrication", ru: "Без выдумок" },
        description: {
          en: "Built-in hallucination detection — nothing is made up or exaggerated.",
          ru: "Встроенная проверка на галлюцинации — ничего не придумано.",
        },
      },
      {
        title: { en: "Any Format In, PDF Out", ru: "Любой формат → PDF" },
        description: {
          en: "Upload LaTeX, markdown, plain text, or HTML. Get a clean, professional PDF.",
          ru: "Загрузите LaTeX, markdown, текст или HTML. Получите чистый PDF.",
        },
      },
    ],
  },
  pricing: {
    heading: { en: "Pricing", ru: "Тарифы" },
    cta: { en: "See Pricing", ru: "Смотреть тарифы" },
  },
  faq: {
    heading: { en: "Frequently Asked Questions", ru: "Часто задаваемые вопросы" },
    items: [
      {
        q: { en: "What is ATS and why does it matter?", ru: "Что такое ATS и почему это важно?" },
        a: {
          en: "ATS (Applicant Tracking System) is software that companies use to filter resumes before a human ever sees them. Up to 75% of resumes are rejected by ATS. HR-Breaker ensures yours gets through.",
          ru: "ATS (Applicant Tracking System) — это ПО, которое компании используют для фильтрации резюме до того, как их увидит человек. До 75% резюме отсеиваются ATS. HR-Breaker помогает пройти этот фильтр.",
        },
      },
      {
        q: { en: "Will my resume contain false information?", ru: "Будет ли в резюме ложная информация?" },
        a: {
          en: "Never. We have built-in hallucination detection that checks every generated resume against your original. Nothing is fabricated or exaggerated.",
          ru: "Никогда. Встроенная проверка на галлюцинации сверяет каждое сгенерированное резюме с оригиналом. Ничего не придумано и не преувеличено.",
        },
      },
      {
        q: { en: "What formats can I upload?", ru: "Какие форматы можно загрузить?" },
        a: {
          en: "PDF, LaTeX, plain text, markdown, or HTML. The output is always a clean, one-page PDF.",
          ru: "PDF, LaTeX, текст, markdown или HTML. На выходе всегда чистый одностраничный PDF.",
        },
      },
      {
        q: { en: "How long does it take?", ru: "Сколько времени это занимает?" },
        a: {
          en: "Usually under a minute. The system generates, checks, and refines your resume automatically.",
          ru: "Обычно меньше минуты. Система генерирует, проверяет и дорабатывает резюме автоматически.",
        },
      },
      {
        q: { en: "Is my data safe?", ru: "Мои данные в безопасности?" },
        a: {
          en: "Your resume data is used only for optimization and is not shared with third parties.",
          ru: "Данные резюме используются только для оптимизации и не передаются третьим лицам.",
        },
      },
    ],
  },
  footer: {
    tagline: { en: "Resume optimization that works.", ru: "Оптимизация резюме, которая работает." },
    links: { en: "Links", ru: "Ссылки" },
    legal: { en: "Legal", ru: "Правовая информация" },
    pricing: { en: "Pricing", ru: "Тарифы" },
    login: { en: "Log In", ru: "Войти" },
    signup: { en: "Sign Up", ru: "Регистрация" },
    privacy: { en: "Privacy Policy", ru: "Политика конфиденциальности" },
    terms: { en: "Terms of Service", ru: "Условия использования" },
    copyright: { en: "© 2026 HR-Breaker. All rights reserved.", ru: "© 2026 HR-Breaker. Все права защищены." },
  },
} as const;
```

**Step 2: Create language context**

```typescript
// frontend/src/app/landing/_lib/LangContext.tsx
"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { type Lang } from "./translations";

const LangContext = createContext<{
  lang: Lang;
  setLang: (lang: Lang) => void;
}>({ lang: "en", setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("en");
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang() {
  return useContext(LangContext);
}
```

**Step 3: Commit**

```bash
git add frontend/src/app/landing/_lib/translations.ts frontend/src/app/landing/_lib/LangContext.tsx
git commit -m "feat(landing): add translations and language context"
```

---

### Task 2: Landing Header

**Files:**
- Create: `frontend/src/app/landing/_components/LandingHeader.tsx`

**Step 1: Create header component**

```tsx
// frontend/src/app/landing/_components/LandingHeader.tsx
"use client";

import Link from "next/link";
import { motion } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingHeader() {
  const { lang, setLang } = useLang();

  return (
    <motion.nav
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl"
    >
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/landing" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <span className="text-sm font-bold text-primary-foreground">HR</span>
          </div>
          <span className="text-lg font-semibold tracking-tight">Breaker</span>
        </Link>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setLang(lang === "en" ? "ru" : "en")}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {lang === "en" ? "RU" : "EN"}
          </button>

          <div className="h-5 w-px bg-border" />

          <Link href="/login">
            <Button variant="ghost" size="sm">
              {t.nav.login[lang]}
            </Button>
          </Link>
          <Link href="/login">
            <Button variant="accent" size="sm">
              {t.nav.signup[lang]}
            </Button>
          </Link>
        </div>
      </div>
    </motion.nav>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/LandingHeader.tsx
git commit -m "feat(landing): add header with language switcher"
```

---

### Task 3: Hero Section

**Files:**
- Create: `frontend/src/app/landing/_components/HeroSection.tsx`

**Step 1: Create hero component**

```tsx
// frontend/src/app/landing/_components/HeroSection.tsx
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
          <Link href="/login">
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
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/HeroSection.tsx
git commit -m "feat(landing): add hero section"
```

---

### Task 4: How It Works Section

**Files:**
- Create: `frontend/src/app/landing/_components/HowItWorksSection.tsx`

**Step 1: Create component**

```tsx
// frontend/src/app/landing/_components/HowItWorksSection.tsx
"use client";

import { FileUp, Link as LinkIcon, Download } from "lucide-react";
import { motion, staggerContainer, staggerItem } from "@/components/motion";
import { Card, CardContent } from "@/components/ui/card";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

const icons = [FileUp, LinkIcon, Download];

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
          className="mt-12 grid gap-6 sm:grid-cols-3"
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
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/HowItWorksSection.tsx
git commit -m "feat(landing): add how-it-works section"
```

---

### Task 5: Features Section

**Files:**
- Create: `frontend/src/app/landing/_components/FeaturesSection.tsx`

**Step 1: Create component**

```tsx
// frontend/src/app/landing/_components/FeaturesSection.tsx
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
                <div>
                  <h3 className="font-semibold">{item.title[lang]}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.description[lang]}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/FeaturesSection.tsx
git commit -m "feat(landing): add features section"
```

---

### Task 6: Pricing Section

**Files:**
- Create: `frontend/src/app/landing/_components/PricingSection.tsx`

**Step 1: Create component**

```tsx
// frontend/src/app/landing/_components/PricingSection.tsx
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
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/PricingSection.tsx
git commit -m "feat(landing): add pricing section"
```

---

### Task 7: FAQ Section

**Files:**
- Create: `frontend/src/app/landing/_components/FAQSection.tsx`

**Step 1: Create component**

```tsx
// frontend/src/app/landing/_components/FAQSection.tsx
"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence, ease } from "@/components/motion";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function FAQSection() {
  const { lang } = useLang();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <section className="py-20">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center text-3xl font-bold">
          {t.faq.heading[lang]}
        </h2>

        <div className="mt-12 space-y-3">
          {t.faq.items.map((item, i) => (
            <div
              key={i}
              className="rounded-xl border border-border/50 bg-card"
            >
              <button
                onClick={() => setOpenIndex(openIndex === i ? null : i)}
                className="flex w-full items-center justify-between p-4 text-left font-medium"
              >
                {item.q[lang]}
                <motion.div
                  animate={{ rotate: openIndex === i ? 180 : 0 }}
                  transition={{ duration: 0.2, ease: ease.snappy }}
                >
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </motion.div>
              </button>

              <AnimatePresence>
                {openIndex === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease: ease.smooth }}
                    className="overflow-hidden"
                  >
                    <p className="px-4 pb-4 text-sm text-muted-foreground">
                      {item.a[lang]}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/FAQSection.tsx
git commit -m "feat(landing): add FAQ accordion section"
```

---

### Task 8: Footer

**Files:**
- Create: `frontend/src/app/landing/_components/LandingFooter.tsx`

**Step 1: Create component**

```tsx
// frontend/src/app/landing/_components/LandingFooter.tsx
"use client";

import Link from "next/link";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingFooter() {
  const { lang } = useLang();

  return (
    <footer className="border-t border-border/50 bg-secondary/50">
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 sm:grid-cols-3">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <span className="text-sm font-bold text-primary-foreground">HR</span>
              </div>
              <span className="text-lg font-semibold tracking-tight">Breaker</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {t.footer.tagline[lang]}
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-sm font-semibold">{t.footer.links[lang]}</h3>
            <ul className="mt-3 space-y-2">
              <li>
                <Link href="/pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  {t.footer.pricing[lang]}
                </Link>
              </li>
              <li>
                <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  {t.footer.login[lang]}
                </Link>
              </li>
              <li>
                <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  {t.footer.signup[lang]}
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="text-sm font-semibold">{t.footer.legal[lang]}</h3>
            <ul className="mt-3 space-y-2">
              <li>
                <span className="text-sm text-muted-foreground">
                  {t.footer.privacy[lang]}
                </span>
              </li>
              <li>
                <span className="text-sm text-muted-foreground">
                  {t.footer.terms[lang]}
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border/50 pt-6">
          <p className="text-center text-xs text-muted-foreground">
            {t.footer.copyright[lang]}
          </p>
        </div>
      </div>
    </footer>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/_components/LandingFooter.tsx
git commit -m "feat(landing): add footer"
```

---

### Task 9: Assemble Landing Page

**Files:**
- Create: `frontend/src/app/landing/page.tsx`

**Step 1: Create the page**

```tsx
// frontend/src/app/landing/page.tsx
"use client";

import { LangProvider } from "./_lib/LangContext";
import { LandingHeader } from "./_components/LandingHeader";
import { HeroSection } from "./_components/HeroSection";
import { HowItWorksSection } from "./_components/HowItWorksSection";
import { FeaturesSection } from "./_components/FeaturesSection";
import { PricingSection } from "./_components/PricingSection";
import { FAQSection } from "./_components/FAQSection";
import { LandingFooter } from "./_components/LandingFooter";

export default function LandingPage() {
  return (
    <LangProvider>
      <div className="min-h-screen bg-background">
        <LandingHeader />
        <main>
          <HeroSection />
          <HowItWorksSection />
          <FeaturesSection />
          <PricingSection />
          <FAQSection />
        </main>
        <LandingFooter />
      </div>
    </LangProvider>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/landing/page.tsx
git commit -m "feat(landing): assemble landing page at /landing"
```

---

### Task 10: Visual QA

**Step 1: Start dev server**

```bash
cd frontend && npm run dev
```

**Step 2: Open `/landing` in browser and verify:**

- All 6 sections render correctly
- Language switcher toggles all content EN↔RU
- CTA buttons link to `/login`
- "See Pricing" links to `/pricing`
- FAQ accordion opens/closes smoothly
- Responsive layout works on mobile viewport
- Animations trigger on scroll
- Existing routes (`/optimize`, `/login`, etc.) still work

**Step 3: Fix any issues found**

**Step 4: Commit fixes if any**

```bash
git add -A
git commit -m "fix(landing): visual QA fixes"
```
