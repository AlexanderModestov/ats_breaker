const steps = [
  {
    number: "01",
    title: "Upload your resume",
    description: "LaTeX, PDF, Markdown, or plain text — any format works.",
  },
  {
    number: "02",
    title: "Paste the job posting",
    description: "Copy the job description or drop in the URL.",
  },
  {
    number: "03",
    title: "Get your tailored resume",
    description: "ATS-optimized PDF ready in seconds, no fabrications.",
  },
];

export function HowItWorksSection() {
  return (
    <section id="how-it-works" className="bg-white py-24">
      <div className="mx-auto max-w-5xl px-4 sm:px-6">
        <h2 className="text-center text-3xl font-bold tracking-tight text-zinc-900">
          How it works
        </h2>
        <div className="mt-16 grid gap-12 sm:grid-cols-3">
          {steps.map((step) => (
            <div key={step.number} className="flex flex-col">
              <span className="text-6xl font-bold text-zinc-200">{step.number}</span>
              <h3 className="mt-4 text-lg font-bold text-zinc-900">{step.title}</h3>
              <p className="mt-2 text-sm text-zinc-500">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
