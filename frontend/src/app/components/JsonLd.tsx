const SITE_URL = "https://hrbreaker.co";

const schema = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#org`,
      name: "HR-Breaker",
      url: `${SITE_URL}/`,
      description:
        "Resume optimization SaaS that rewrites your resume to match any job posting, runs ATS simulation, and returns an optimized PDF.",
      sameAs: [],
    },
    {
      "@type": "SoftwareApplication",
      name: "HR-Breaker",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      description:
        "Optimize your resume for any job posting. Pass ATS filters with confidence.",
      offers: [
        {
          "@type": "Offer",
          name: "Starter",
          price: "0",
          priceCurrency: "EUR",
        },
        {
          "@type": "Offer",
          name: "Job Hunter",
          priceCurrency: "EUR",
        },
        {
          "@type": "Offer",
          name: "Offer Mode",
          priceCurrency: "EUR",
        },
      ],
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "What is ATS and why does it matter?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "ATS (Applicant Tracking System) is software used by employers to filter resumes before a human reviews them. Over 75% of large companies use ATS, meaning your resume must be formatted and keyword-optimized to pass automated screening.",
          },
        },
        {
          "@type": "Question",
          name: "Will my resume contain false information?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "No. HR-Breaker includes hallucination detection that compares every claim in the optimized resume against your uploaded source material. Nothing is fabricated or exaggerated.",
          },
        },
        {
          "@type": "Question",
          name: "What formats can I upload?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "You can upload your resume in PDF, LaTeX, Markdown, HTML, or plain text. HR-Breaker converts all formats into a single-column, ATS-parsable PDF.",
          },
        },
        {
          "@type": "Question",
          name: "How long does it take?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "HR-Breaker generates your optimized resume in seconds. Upload your resume, paste the job posting, and receive a tailored PDF immediately.",
          },
        },
        {
          "@type": "Question",
          name: "Is my data safe?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Yes. HR-Breaker uses encrypted connections and does not share your resume data with third parties.",
          },
        },
      ],
    },
  ],
};

export function JsonLd() {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
