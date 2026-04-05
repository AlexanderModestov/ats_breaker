# Landing Page Design

## Overview

A landing page at `/landing` that promotes the HR-Breaker service and drives users to sign up. Bilingual (EN/RU) with a language switcher. Uses the existing design system (Tailwind, Framer Motion, Satoshi + Inter fonts, teal accent).

The landing page is independent from the main app — default routes remain unchanged.

## Sections

### 1. Header (Sticky)

- Logo "HR-Breaker" left-aligned
- Right side: language switcher (EN/RU), "Log In" button, "Sign Up" button (accent)
- Backdrop blur style matching current Navbar

### 2. Hero

Centered, spacious layout. Staggered `fadeSlideUp` animation.

**EN:**
- Heading (Satoshi, bold): "Stop getting filtered out. Start getting interviews."
- Subheading (Inter, muted): "Optimize your resume for any job posting. Pass ATS filters with confidence."
- CTA button (accent/teal): "Get Started" → `/login`
- Small text below: "Free to try. No credit card required."

**RU:**
- Heading: "Хватит терять отклики. Начните получать собеседования."
- Subheading: "Адаптируйте резюме под любую вакансию. Пройдите ATS-фильтры уверенно."
- CTA: "Начать" → `/login`

### 3. How It Works

Heading: "How It Works" / "Как это работает"

Three cards in a row (vertical on mobile). `staggerContainer` + `staggerItem` on scroll.

| # | Icon (Lucide) | EN Title | EN Description | RU Title | RU Description |
|---|---------------|----------|----------------|----------|----------------|
| 1 | `FileUp` | Upload Your Resume | Paste or upload your resume in any format — PDF, LaTeX, plain text. | Загрузите резюме | Вставьте или загрузите резюме в любом формате — PDF, LaTeX, текст. |
| 2 | `Link` | Add a Job Posting | Paste a job URL or description. We extract the key requirements automatically. | Добавьте вакансию | Вставьте ссылку или описание. Мы автоматически извлечём ключевые требования. |
| 3 | `Download` | Get Your Optimized Resume | Receive a tailored, ATS-ready PDF resume in seconds. | Получите оптимизированное резюме | Получите адаптированное PDF-резюме, готовое к ATS, за секунды. |

### 4. Features (Why HR-Breaker)

Heading: "Why HR-Breaker" / "Почему HR-Breaker"

2×2 grid (single column on mobile). Light cards without border, teal icon. `fadeSlideUp` on viewport enter.

| Icon (Lucide) | EN Title | EN Description | RU Title | RU Description |
|---------------|----------|----------------|----------|----------------|
| `ShieldCheck` | ATS-Optimized | Your resume is tested against real ATS simulation before you get it. | Оптимизация под ATS | Резюме проверяется симуляцией ATS перед выдачей. |
| `Target` | Keyword Matching | We analyze the job posting and ensure your resume hits the right keywords. | Подбор ключевых слов | Анализируем вакансию и обеспечиваем попадание по ключевым словам. |
| `Eye` | No Fabrication | Built-in hallucination detection — nothing is made up or exaggerated. | Без выдумок | Встроенная проверка на галлюцинации — ничего не придумано. |
| `FileText` | Any Format In, PDF Out | Upload LaTeX, markdown, plain text, or HTML. Get a clean, professional PDF. | Любой формат → PDF | Загрузите LaTeX, markdown, текст или HTML. Получите чистый PDF. |

### 5. Pricing

Heading: "Pricing" / "Тарифы"

Single CTA button: "See Pricing" / "Смотреть тарифы" → link to `/pricing`.

### 6. FAQ

Heading: "Frequently Asked Questions" / "Часто задаваемые вопросы"

Accordion style, `max-w-2xl` centered. `AnimatePresence` for expand/collapse.

| EN Question | EN Answer | RU Question | RU Answer |
|-------------|-----------|-------------|-----------|
| What is ATS and why does it matter? | ATS (Applicant Tracking System) is software that companies use to filter resumes before a human ever sees them. Up to 75% of resumes are rejected by ATS. HR-Breaker ensures yours gets through. | Что такое ATS и почему это важно? | ATS (Applicant Tracking System) — это ПО, которое компании используют для фильтрации резюме до того, как их увидит человек. До 75% резюме отсеиваются ATS. HR-Breaker помогает пройти этот фильтр. |
| Will my resume contain false information? | Never. We have built-in hallucination detection that checks every generated resume against your original. Nothing is fabricated or exaggerated. | Будет ли в резюме ложная информация? | Никогда. Встроенная проверка на галлюцинации сверяет каждое сгенерированное резюме с оригиналом. Ничего не придумано и не преувеличено. |
| What formats can I upload? | PDF, LaTeX, plain text, markdown, or HTML. The output is always a clean, one-page PDF. | Какие форматы можно загрузить? | PDF, LaTeX, текст, markdown или HTML. На выходе всегда чистый одностраничный PDF. |
| How long does it take? | Usually under a minute. The system generates, checks, and refines your resume automatically. | Сколько времени это занимает? | Обычно меньше минуты. Система генерирует, проверяет и дорабатывает резюме автоматически. |
| Is my data safe? | Your resume data is used only for optimization and is not shared with third parties. | Мои данные в безопасности? | Данные резюме используются только для оптимизации и не передаются третьим лицам. |

### 7. Footer

Dark background (`secondary`). Three columns on desktop, single on mobile.

**Column 1 — Brand:**
- Logo "HR-Breaker"
- Tagline: "Resume optimization that works."

**Column 2 — Links:**
- Pricing
- Log In
- Sign Up

**Column 3 — Legal:**
- Privacy Policy
- Terms of Service

**Bottom:** Divider + "© 2026 HR-Breaker. All rights reserved."

## Technical Details

- **Route:** `/landing` — standalone page, no auth required
- **Internationalization:** React context/state for language toggle (EN/RU). No i18n library — simple object map for strings.
- **Components:** Reuse existing UI components (`Button`, `Card`) and motion helpers (`fadeSlideUp`, `staggerContainer`, etc.)
- **Responsive:** Mobile-first, breakpoints follow existing Tailwind config
- **No shared layout with main app** — landing has its own header/footer, not the app Navbar
