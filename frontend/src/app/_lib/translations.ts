export type Lang = "en" | "ru";

export const t = {
  nav: {
    login: { en: "Log In", ru: "Войти" },
    signup: { en: "Sign Up", ru: "Регистрация" },
  },
  hero: {
    heading: {
      en: "Get more Job Offers with AI: optimize your resume & prepare for Interviews",
      ru: "Получайте больше офферов с AI: оптимизируйте резюме и готовьтесь к собеседованиям",
    },
    subheading: {
      en: "Tailor your resume for any job description, pass ATS systems, and practice real interview questions with an AI coach — all in one place",
      ru: "Адаптируйте резюме под любое описание вакансии, проходите ATS-системы и тренируйтесь отвечать на реальные вопросы с AI-коучем — всё в одном месте",
    },
    cta: { en: "Start Getting Offers", ru: "Начните получать офферы" },
    ctaSub: {
      en: "Free to try. No credit card required.",
      ru: "Попробуйте бесплатно. Карта не нужна.",
    },
  },
  applicationToOffer: {
    heading: {
      en: "How You Go from Application to Offer",
      ru: "Как пройти путь от отклика до оффера",
    },
    subheading: {
      en: "Everything you need to go from application to offer:",
      ru: "Всё, что нужно, чтобы пройти путь от отклика до оффера:",
    },
    cards: [
      {
        title: { en: "Optimize Your Resume for ATS", ru: "Оптимизируйте резюме под ATS" },
        description: {
          en: "Automatically match keywords and requirements from any job description",
          ru: "Автоматически подбирайте ключевые слова и требования из любой вакансии",
        },
      },
      {
        title: {
          en: "Practice real interview questions with AI",
          ru: "Тренируйтесь на реальных вопросах с AI",
        },
        description: {
          en: "Present your experience clearly and confidently",
          ru: "Презентуйте свой опыт ясно и уверенно",
        },
      },
    ],
    cta: { en: "Get Interview-Ready", ru: "Готовьтесь к собеседованию" },
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
      {
        title: {
          en: "Practice Interviews with AI Coach",
          ru: "Тренируйтесь на собеседованиях с AI-коучем",
        },
        description: {
          en: "Train answers, improve clarity, and get instant feedback.",
          ru: "Тренируйте ответы, улучшайте ясность и получайте мгновенный фидбек.",
        },
      },
    ],
    cta: { en: "Get Me More Interviews", ru: "Хочу больше собеседований" },
  },
  aiCoach: {
    heading: {
      en: "AI Interview Coach That Actually Prepares You",
      ru: "AI-коуч, который реально готовит к собеседованию",
    },
    intro: {
      en: "Practice answering real interview questions based on your resume and target job.",
      ru: "Отвечайте на реальные вопросы собеседований на основе вашего резюме и желаемой вакансии.",
    },
    feedbackHeading: {
      en: "Get feedback on:",
      ru: "Получайте обратную связь по:",
    },
    feedbackItems: [
      {
        title: { en: "Clarity and structure", ru: "Ясности и структуре" },
        description: {
          en: "Make every answer easy to follow.",
          ru: "Каждый ответ — лёгкий для восприятия.",
        },
      },
      {
        title: { en: "Relevance to the role", ru: "Соответствию роли" },
        description: {
          en: "Stay focused on what the hiring manager cares about.",
          ru: "Фокус на том, что важно для нанимающего менеджера.",
        },
      },
      {
        title: { en: "Impact of your answers", ru: "Силе ваших ответов" },
        description: {
          en: "Highlight outcomes, not just responsibilities.",
          ru: "Подчёркивайте результаты, а не только обязанности.",
        },
      },
    ],
    outro: {
      en: "Turn your experience into strong, confident stories that hiring managers understand.",
      ru: "Превратите свой опыт в сильные, уверенные истории, понятные нанимающим менеджерам.",
    },
    cta: { en: "Start Interview Training", ru: "Начать тренировку собеседований" },
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
    subtitle: {
      en: "Choose the plan that fits your job search",
      ru: "Выберите тариф под ваш поиск работы",
    },
    monthly: { en: "/month", ru: "/мес" },
    cta: { en: "See Pricing", ru: "Смотреть тарифы" },
    plans: [
      {
        name: { en: "Starter", ru: "Starter" },
        tagline: { en: "Try it out", ru: "Попробуйте" },
        price: { en: "Free", ru: "Бесплатно" },
        priceSuffix: { en: "", ru: "" },
        features: [
          { en: "3 resume optimizations / week", ru: "3 оптимизации резюме / нед" },
          { en: "Basic ATS optimization", ru: "Базовая оптимизация под ATS" },
          { en: "Keyword highlights", ru: "Подсветка ключевых слов" },
          { en: "AI Interview Prep (limited)", ru: "AI-подготовка к интервью (ограниченно)" },
          { en: "PDF download", ru: "Скачивание в PDF" },
        ],
        highlighted: false,
      },
      {
        name: { en: "Job Hunter", ru: "Job Hunter" },
        tagline: { en: "Get more interviews", ru: "Больше собеседований" },
        price: { en: "€19", ru: "€19" },
        priceSuffix: { en: "/month", ru: "/мес" },
        features: [
          { en: "Everything in Starter +", ru: "Всё из Starter +" },
          { en: "Unlimited resume optimizations", ru: "Безлимитные оптимизации" },
          { en: "Full ATS score", ru: "Полный ATS-скоринг" },
          { en: "Missing keywords & improvements", ru: "Недостающие слова и улучшения" },
          { en: "Multiple formats (PDF, DOCX)", ru: "Несколько форматов (PDF, DOCX)" },
          { en: "Version history", ru: "История версий" },
        ],
        highlighted: true,
      },
      {
        name: { en: "Offer Mode", ru: "Offer Mode" },
        tagline: { en: "Get the offer", ru: "Получите оффер" },
        price: { en: "€29", ru: "€29" },
        priceSuffix: { en: "/month", ru: "/мес" },
        features: [
          { en: "Everything in Job Hunter +", ru: "Всё из Job Hunter +" },
          { en: "AI interview prep", ru: "AI-подготовка к интервью" },
          { en: "Answers to common questions", ru: "Ответы на частые вопросы" },
          { en: "STAR-structured responses", ru: "Ответы по методу STAR" },
          { en: "Personalized feedback", ru: "Персональная обратная связь" },
          { en: "Gap analysis", ru: "Анализ пробелов" },
          { en: "Cover letter generator", ru: "Генератор сопроводительных писем" },
        ],
        highlighted: false,
      },
    ],
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
