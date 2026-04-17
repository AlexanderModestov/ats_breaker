# GEO Audit Report: HR-Breaker

**Audit Date:** 2026-04-16 (re-audit #2)
**URL:** https://hrbreaker.co/
**Business Type:** SaaS — Resume optimization / ATS tool (early-stage)
**Stack:** Next.js (SSR/prerendered) on Vercel, Supabase backend
**Pages Analyzed:** 2 public (/, /pricing) + /signin probed
**Previous Audit:** 2026-04-16 (baseline) — Score: 20/100

---

## Executive Summary

**Overall GEO Score: 22/100 (Critical) — up from 20/100**

HR-Breaker deployed `robots.txt` and `sitemap.xml` since the baseline audit — both are now live and correctly configured with explicit AI crawler permissions. This fixes two Critical-tier issues and lifts Technical GEO from 45 to 55. However, the site remains in Critical territory because the highest-leverage items — structured data (JSON-LD), Open Graph tags, canonical URL, llms.txt, and content/brand authority signals — have not yet been addressed. The foundation is now better, but the categories that carry 75% of the GEO score weight (Citability, Brand, E-E-A-T) are unchanged.

### Score Breakdown

| Category | Score | Previous | Delta | Weight | Weighted |
|---|---|---|---|---|---|
| AI Citability | 30/100 | 30 | — | 25% | 7.50 |
| Brand Authority | 10/100 | 10 | — | 20% | 2.00 |
| Content E-E-A-T | 15/100 | 15 | — | 20% | 3.00 |
| Technical GEO | 55/100 | 45 | **+10** | 15% | 8.25 |
| Schema & Structured Data | 0/100 | 0 | — | 10% | 0.00 |
| Platform Optimization | 10/100 | 10 | — | 10% | 1.00 |
| **Overall GEO Score** | | | **+2** | | **21.75 ≈ 22/100** |

### What Improved Since Baseline

| Fix | Status | Impact |
|---|---|---|
| robots.txt with AI crawler allows | ✅ Deployed | Technical +5 |
| sitemap.xml (2 URLs) | ✅ Deployed | Technical +5 |
| llms.txt | ❌ Not deployed | — |
| JSON-LD schema | ❌ Not added | — |
| Open Graph / Twitter Cards | ❌ Not added | — |
| Canonical URL | ❌ Not added | — |
| Privacy / Terms pages | ❌ Still 404 | — |
| Favicon | ❌ Still 404 | — |

---

## Remaining Critical Issues (Fix Immediately)

### C1. ~~No robots.txt~~ — FIXED ✅
Now live with 17 AI crawlers explicitly allowed, /signin and /api/ disallowed, sitemap declared. Excellent implementation.

### C2. ~~No sitemap.xml~~ — FIXED ✅
Now live with 2 URLs (/, /pricing), dynamic `lastModified`, correct priorities. Will need updating when /about, /privacy, /terms, /blog pages ship.

### C3. No structured data (still 0 JSON-LD)
Zero JSON-LD, microdata, or RDFa anywhere on the site. For a SaaS with pricing tiers and FAQ content, this is the single highest-leverage fix remaining.

**Fix:** Add this JSON-LD to the homepage layout:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://hrbreaker.co/#org",
      "name": "HR-Breaker",
      "url": "https://hrbreaker.co/",
      "description": "Resume optimization SaaS that rewrites your resume to match any job posting, runs ATS simulation, and returns an optimized PDF.",
      "sameAs": []
    },
    {
      "@type": "SoftwareApplication",
      "name": "HR-Breaker",
      "applicationCategory": "BusinessApplication",
      "operatingSystem": "Web",
      "description": "Optimize your resume for any job posting. Pass ATS filters with confidence.",
      "offers": [
        { "@type": "Offer", "name": "Starter", "price": "0", "priceCurrency": "EUR" },
        { "@type": "Offer", "name": "Job Hunter", "priceCurrency": "EUR" },
        { "@type": "Offer", "name": "Offer Mode", "priceCurrency": "EUR" }
      ]
    },
    {
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "What is ATS and why does it matter?",
          "acceptedAnswer": { "@type": "Answer", "text": "ATS (Applicant Tracking System) is software used by employers to filter resumes before a human reviews them. Over 75% of large companies use ATS, meaning your resume must be formatted and keyword-optimized to pass automated screening." }
        },
        {
          "@type": "Question",
          "name": "Will my resume contain false information?",
          "acceptedAnswer": { "@type": "Answer", "text": "No. HR-Breaker includes hallucination detection that compares every claim in the optimized resume against your uploaded source material. Nothing is fabricated or exaggerated." }
        },
        {
          "@type": "Question",
          "name": "What formats can I upload?",
          "acceptedAnswer": { "@type": "Answer", "text": "You can upload your resume in PDF, LaTeX, Markdown, HTML, or plain text. HR-Breaker converts all formats into a single-column, ATS-parsable PDF." }
        },
        {
          "@type": "Question",
          "name": "How long does it take?",
          "acceptedAnswer": { "@type": "Answer", "text": "HR-Breaker generates your optimized resume in seconds. Upload your resume, paste the job posting, and receive a tailored PDF immediately." }
        },
        {
          "@type": "Question",
          "name": "Is my data safe?",
          "acceptedAnswer": { "@type": "Answer", "text": "Yes. HR-Breaker uses encrypted connections and does not share your resume data with third parties." }
        }
      ]
    }
  ]
}
```

### C4. Broken legal links (/privacy, /terms → 404)
Footer still references Privacy Policy and Terms of Service but both return 404. This remains a critical trust failure — especially for a SaaS handling resumes (PII) with EUR pricing (GDPR jurisdiction).

**Fix:** Publish real Privacy Policy and Terms of Service at `/privacy` and `/terms`. Add them to `sitemap.ts` once live.

### C5. No canonical URL
No `<link rel="canonical">` present. Risk of duplicate indexing.

**Fix:** Add via Next.js Metadata API:
```ts
export const metadata: Metadata = {
  alternates: { canonical: 'https://hrbreaker.co/' },
}
```

---

## High Priority Issues

### H1. Title tag is just "HR-Breaker"
No keywords, no value proposition. Unchanged from baseline.

**Fix:** `HR-Breaker — ATS Resume Optimization for Any Job Posting`

### H2. Meta description is 45 chars
"Resume optimization tool for job postings" — too short, too generic. Unchanged.

**Fix:** "HR-Breaker optimizes your resume to match any job posting, runs an ATS simulation, and returns a tailored PDF in seconds. Free to try — no credit card required." (158 chars)

### H3. No Open Graph / Twitter Card meta tags
Links shared on LinkedIn, Slack, X, Discord show no preview. This directly suppresses the brand-mention velocity that AI models weight heavily.

**Fix:** Add OG + Twitter meta via Next.js Metadata API with a 1200×630 social share image.

### H4. No llms.txt
Still 404. The file was generated in `deliverables/hrbreaker/public/llms.txt` but not deployed.

**Fix:** Copy `public/llms.txt` from the deliverables into the Next.js project's `public/` directory and redeploy.

### H5. No author, team, or about page
Zero E-E-A-T signals. No identifiable entity behind the product.

### H6. Unsupported "hallucination detection" claim
Still no methodology page explaining how this works.

### H7. FAQ answers not in server-rendered HTML
5 FAQ questions visible but answers still hydrate client-side. AI crawlers and Google AIO may not see them.

### H8. No favicon
Still 404 at `/favicon.ico`.

---

## Medium Priority Issues

### M1. H1 opacity:0 inline style (animation)
Hero text starts invisible; some non-JS crawlers may not see it.

### M2. Zero images
No screenshots, no product UI, no visual content for multimodal AI.

### M3. No blog or content surface
Nothing to cite beyond the homepage.

### M4. No testimonials, case studies, or stats
No social proof, no quotable numbers.

### M5. EUR pricing but no localization or hreflang
Single-language site targeting European market.

### M6. Duplicate title + meta description across / and /pricing
Both pages have identical `<title>HR-Breaker</title>` and same meta description.

### M7. No social or brand links in footer
No LinkedIn, X, YouTube, Product Hunt, or GitHub links.

---

## Low Priority Issues

### L1. No X-Frame-Options header (CSP covers it)
### L2. No .well-known/security.txt
### L3. Edge cache age ~9 days (fine for static marketing page)

---

## Category Deep Dives

### AI Citability — 30/100 (unchanged)

Content remains thin (~330 words visible text), with short feature bullets averaging ~15 words each. No statistics, no self-contained answer blocks, no comparison tables. FAQ section has 5 questions but answers are client-rendered, reducing citability for crawlers that don't execute JavaScript.

**Key gaps:**
- 0 passages with citable statistics
- 0 self-contained 40-80 word answer blocks
- FAQ answers not in SSR HTML
- No comparison content (HR-Breaker vs. manual optimization, etc.)

### Brand Authority — 10/100 (unchanged)

No social accounts linked, no press, no testimonials, no third-party mentions visible. Domain is brandable but has no external entity signals. AI models cannot triangulate HR-Breaker as a known entity.

### Content E-E-A-T — 15/100 (unchanged)

No author, no about page, no team, no credentials, no contact info beyond the product. Broken /privacy and /terms links actively hurt trustworthiness. "Hallucination detection" claim remains unsupported.

### Technical GEO — 55/100 (was 45, +10)

**Improvements:**
- ✅ robots.txt deployed with 17 AI crawlers explicitly allowed
- ✅ sitemap.xml deployed with dynamic lastModified
- ✅ Sitemap declared in robots.txt

**Still missing:**
- ❌ No llms.txt (404)
- ❌ No canonical URL
- ❌ No OG / Twitter meta
- ❌ No favicon
- ❌ Broken /privacy and /terms links
- ❌ No X-Frame-Options header

**Unchanged strengths:**
- ✅ SSR via Next.js prerender
- ✅ HTTPS with HSTS (max-age=63072000)
- ✅ Strong CSP with frame-ancestors 'none'
- ✅ Fast TTFB via Vercel edge
- ✅ HTML lang="en"

### Schema & Structured Data — 0/100 (unchanged)

Absolute zero. No JSON-LD, microdata, or RDFa. The full schema template is provided above in C3.

### Platform Optimization — 10/100 (unchanged)

| Platform | Readiness | Change |
|---|---|---|
| Google AI Overviews | Low | Slightly better (crawlers can now reach content) |
| ChatGPT | Low | GPTBot now explicitly allowed — but nothing quotable |
| Perplexity | Very low | PerplexityBot allowed but no citable content |
| Gemini | Low | Same as AIO |
| Bing Copilot | Low | No Bing Webmaster submission yet |

---

## Quick Wins (Remaining — This Week)

1. **Deploy llms.txt** — file already generated, just copy to `public/`. (5 min)
2. **Add JSON-LD schema** — Organization + SoftwareApplication + FAQPage. Template in C3 above. (2 hr)
3. **Set unique title + meta description per page** via `generateMetadata`. (30 min)
4. **Add canonical URL** site-wide. (15 min)
5. **Add OG + Twitter Card meta** with a share image. (1 hr)
6. **Ship Privacy Policy + Terms of Service pages.** (half-day)
7. **Add favicon + apple-touch-icon.** (15 min)
8. **Server-render FAQ answers** — move from client hydration to SSR HTML. (1-2 hr)

**Expected score if all 8 done: 22 → ~45 (Poor tier — exit from Critical).**

---

## 30-Day Action Plan

### Week 1: Technical Foundations (target: 45/100)
- [x] ~~Deploy robots.txt with AI crawler allows~~ ✅
- [x] ~~Deploy sitemap.xml~~ ✅
- [ ] Deploy llms.txt
- [ ] Add JSON-LD schema (Organization + SoftwareApplication + FAQPage)
- [ ] Unique title + meta description per route
- [ ] Add canonical URL, OG + Twitter meta, favicon
- [ ] Publish Privacy Policy + Terms of Service
- [ ] Server-render FAQ answers in HTML

### Week 2: Trust & Content Depth (target: 55/100)
- [ ] Publish /about with founder bio, photo, LinkedIn
- [ ] Publish /trust or /how-it-works explaining hallucination detection
- [ ] Add 2-3 product screenshots with descriptive alt text
- [ ] Add 1 hero statistic with credible source citation
- [ ] Launch LinkedIn Company Page + X/Twitter; link from footer

### Week 3: Brand Authority (target: 65/100)
- [ ] Product Hunt launch
- [ ] Record + publish 2-3 min YouTube demo
- [ ] Collect 5 testimonials with real names + LinkedIn
- [ ] First blog post: "How ATS Keyword Matching Actually Works"

### Week 4: Content Engine (target: 70/100)
- [ ] 2 more cornerstone blog posts
- [ ] Add Article schema to blog
- [ ] Submit sitemap to Google Search Console + Bing Webmaster
- [ ] Re-run `/geo audit` — compare via `/geo compare hrbreaker.co`

---

## Appendix A: robots.txt Review (DEPLOYED)

```
User-agent: *          → Allow: / | Disallow: /signin, /api/, /_next/
17 AI crawlers         → All explicitly Allow: /
Sitemap                → https://hrbreaker.co/sitemap.xml
```

**Verdict:** Excellent. Matches the recommended template exactly. All major AI crawlers (GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, Claude-Web, anthropic-ai, PerplexityBot, Perplexity-User, Google-Extended, Applebot-Extended, CCBot, Bytespider, Amazonbot, Meta-ExternalAgent, FacebookBot, cohere-ai, DuckAssistBot) are permitted.

## Appendix B: sitemap.xml Review (DEPLOYED)

| URL | lastmod | changefreq | priority |
|---|---|---|---|
| https://hrbreaker.co/ | 2026-04-16T22:38:28.263Z | weekly | 1 |
| https://hrbreaker.co/pricing | 2026-04-16T22:38:28.263Z | monthly | 0.9 |

**Verdict:** Correct. Dynamic lastModified from `app/sitemap.ts`. Will need expansion when /about, /privacy, /terms, /blog pages ship.

## Appendix C: Pages Analyzed

| URL | Status | Title | GEO Issues |
|---|---|---|---|
| / | 200 | HR-Breaker | 15 remaining |
| /pricing | 200 | HR-Breaker (duplicate) | 4 |
| /signin | 200 | (auth page — excluded) | — |
| /robots.txt | **200 ✅** | — | Fixed |
| /sitemap.xml | **200 ✅** | — | Fixed |
| /llms.txt | 404 | — | H4 |
| /privacy | 404 | — | C4 |
| /terms | 404 | — | C4 |
| /about | 404 | — | H5 |
| /blog | 404 | — | M3 |
| /favicon.ico | 404 | — | H8 |

---

**Next steps:** Deploy llms.txt + JSON-LD schema + OG meta this week. Re-audit with `/geo audit https://hrbreaker.co/` after those land — target score: 45/100 (exit Critical tier).
