"use client";

import { Zap, Target, FileText, History, MessageCircle, Download } from "lucide-react";

const features = [
  { icon: Zap, title: "Instant optimization", description: "Tailored resume in under 10 seconds." },
  { icon: Target, title: "ATS simulation", description: "Know exactly which filters you pass." },
  { icon: FileText, title: "Any format", description: "Upload LaTeX, PDF, Markdown, or plain text." },
  { icon: History, title: "Version history", description: "Every optimization saved, always accessible." },
  { icon: MessageCircle, title: "AI coach", description: "Interview prep and STAR answers on demand." },
  { icon: Download, title: "Multiple exports", description: "Download as PDF or DOCX, ready to send." },
];

export function FeaturesSection() {
  return (
    <section className="bg-white py-24">
      <div className="mx-auto max-w-5xl px-4 sm:px-6">
        <h2 className="text-center text-3xl font-bold tracking-tight text-zinc-900">
          Everything you need
        </h2>
        <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="rounded-lg border border-zinc-200 bg-white p-6"
              >
                <Icon className="h-5 w-5 text-zinc-400" />
                <h3 className="mt-4 font-semibold text-zinc-900">{feature.title}</h3>
                <p className="mt-1 text-sm text-zinc-500">{feature.description}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
