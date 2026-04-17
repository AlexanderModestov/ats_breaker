export function JsonLd() {
  const schema = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": "https://hrbreaker.co/#org",
        name: "HR-Breaker",
        url: "https://hrbreaker.co/",
        description:
          "Resume optimization SaaS with ATS simulation and hallucination detection.",
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
            price: "20",
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
              text: "ATS (Applicant Tracking System) is software used by employers to automatically screen resumes. Over 75% of large companies use ATS, meaning your resume must be keyword-optimized and properly formatted to pass automated filters before a human ever sees it.",
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
              text: "PDF, LaTeX, Markdown, HTML, and plain text. HR-Breaker converts all formats into a single-column, ATS-parsable PDF.",
            },
          },
          {
            "@type": "Question",
            name: "How long does it take?",
            acceptedAnswer: {
              "@type": "Answer",
              text: "Seconds. Upload your resume, paste the job posting, and receive a tailored, ATS-ready PDF immediately.",
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

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
