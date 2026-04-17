import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — Free, Job Hunter, and Offer Mode Plans",
  description:
    "HR-Breaker pricing: start free with no credit card, upgrade to Job Hunter for unlimited ATS optimizations, or go Offer Mode for interview prep and cover letters.",
  alternates: {
    canonical: "/pricing",
  },
  openGraph: {
    type: "website",
    url: "https://hrbreaker.co/pricing",
    title: "HR-Breaker Pricing — Free to Try, €20/mo Pro",
    description:
      "Compare HR-Breaker plans. Free Starter tier, €20/month Pro with 50 optimizations, add-on packs available.",
  },
};

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
