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
    subtitle: {
      en: "Choose the plan that fits your job search",
      ru: "Выберите тариф под ваш поиск работы",
    },
    monthly: { en: "/month", ru: "/мес" },
    cta: { en: "See Pricing", ru: "Смотреть тарифы" },
    plans: [
      {
        name: { en: "Free", ru: "Free" },
        price: "0",
        description: {
          en: "Try it out with limited monthly usage",
          ru: "Попробуйте с ограниченным количеством в месяц",
        },
        features: [
          { en: "3 resume optimizations / month", ru: "3 оптимизации резюме / мес" },
          { en: "ATS simulation check", ru: "Проверка ATS-симуляцией" },
          { en: "PDF export", ru: "Экспорт в PDF" },
          { en: "Keyword matching", ru: "Подбор ключевых слов" },
        ],
        cta: { en: "Get Started", ru: "Начать" },
        highlighted: false,
      },
      {
        name: { en: "Pro", ru: "Pro" },
        price: "19",
        description: {
          en: "Unlimited optimizations for active job seekers",
          ru: "Безлимитные оптимизации для активного поиска",
        },
        features: [
          { en: "Unlimited optimizations", ru: "Безлимитные оптимизации" },
          { en: "ATS simulation + AI detection", ru: "ATS-симуляция + AI-детекция" },
          { en: "Hallucination detection", ru: "Проверка на галлюцинации" },
          { en: "Vector similarity matching", ru: "Векторное сравнение" },
          { en: "Priority rendering", ru: "Приоритетная обработка" },
        ],
        cta: { en: "Go Pro", ru: "Выбрать Pro" },
        highlighted: true,
      },
      {
        name: { en: "Mentor", ru: "Mentor" },
        price: "50",
        description: {
          en: "Everything in Pro, plus personal HR coach",
          ru: "Всё из Pro + персональный HR-коуч",
        },
        features: [
          { en: "Everything in Pro", ru: "Всё из тарифа Pro" },
          { en: "1-on-1 HR coach sessions", ru: "Индивидуальные сессии с HR-коучем" },
          { en: "Resume strategy review", ru: "Стратегический разбор резюме" },
          { en: "Interview preparation tips", ru: "Подготовка к собеседованиям" },
          { en: "LinkedIn profile advice", ru: "Рекомендации по LinkedIn" },
        ],
        cta: { en: "Get Mentor", ru: "Выбрать Mentor" },
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
