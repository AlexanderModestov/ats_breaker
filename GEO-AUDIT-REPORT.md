# GEO Audit Report: HR-Breaker

**Audit Date:** 2026-04-17 (re-audit #8)
**URL:** https://hrbreaker.co/
**Business Type:** SaaS — Resume optimization / ATS tool
**Stack:** Next.js on Vercel, Supabase
**Pages Analyzed:** 2 public (/, /pricing)
**Baseline (Apr 16):** 20/100 → **Current: 32/100 (+12)**

---

## Executive Summary

**Overall GEO Score: 32/100 (Critical) — up from 20/100 baseline (+12)**

HR-Breaker has made significant technical progress over 2 days, deploying robots.txt, sitemap.xml, llms.txt, optimized meta tags, OG/Twitter cards, canonical URLs, and now JSON-LD schema (Organization + SoftwareApplication + FAQPage). Schema jumped from 0 to 62 in a single deploy — the biggest single-fix improvement. Technical GEO is now at 72/100, well into "Good" territory. The site remains in Critical tier overall because the three categories that carry 65% of the weight — Citability (35), Brand (10), and E-E-A-T (15) — require content and off-site work that can't be solved with config files alone.

### Score Breakdown

| Category | Score | Previous | Delta | Weight | Weighted |
|---|---|---|---|---|---|
| AI Citability | 35/100 | 32 | +3 | 25% | 8.75 |
| Brand Authority | 10/100 | 10 | — | 20% | 2.00 |
| Content E-E-A-T | 15/100 | 15 | — | 20% | 3.00 |
| Technical GEO | 72/100 | 70 | +2 | 15% | 10.80 |
| Schema & Structured Data | 62/100 | 0 | **+62** | 10% | 6.20 |
| Platform Optimization | 12/100 | 12 | — | 10% | 1.20 |
| **Overall GEO Score** | | | **+7** | | **31.95 ≈ 32/100** |

### Score History

| Date | Score | What Changed |
|---|---|---|
| Apr 16 (baseline) | 20 | First audit — nothing deployed |
| Apr 16 (audit 2) | 22 | +robots.txt, +sitemap.xml |
| Apr 17 (audit 4) | 25 | +llms.txt, +title/meta, +canonical, +OG/Twitter |
| Apr 17 (audit 8) | **32** | **+JSON-LD (Org + SoftwareApp + FAQPage)** |

### Full Progress Tracker

| Fix | Status | Score Impact |
|---|---|---|
| robots.txt (17 AI crawlers) | ✅ Apr 16 | Tech +5 |
| sitemap.xml (dynamic, 2 URLs) | ✅ Apr 16 | Tech +5 |
| llms.txt | ✅ Apr 17 | Tech +5 |
| Title tags (unique, keyword-rich) | ✅ Apr 17 | Citability +1, Tech +1 |
| Meta descriptions (150+ chars) | ✅ Apr 17 | Citability +1, Tech +1 |
| Canonical URLs (per page) | ✅ Apr 17 | Tech +3 |
| OG meta (title, desc, url, type, locale) | ✅ Apr 17 | Tech +2, Platform +1 |
| Twitter Card meta (summary_large_image) | ✅ Apr 17 | Tech +1, Platform +1 |
| robots meta "index, follow" | ✅ Apr 17 | Tech +1 |
| JSON-LD: Organization | ✅ Apr 17 | Schema +20 |
| JSON-LD: SoftwareApplication + Offers | ✅ Apr 17 | Schema +20 |
| JSON-LD: FAQPage (5 Q&As) | ✅ Apr 17 | Schema +22, Citability +3 |
| og:image | ❌ Missing | — |
| /privacy page | ❌ 404 | — |
| /terms page | ❌ 404 | — |
| /about page | ❌ 404 | — |
| Favicon | ❌ 404 | — |
| Social profiles (LinkedIn, X) | ❌ Missing | — |
| Blog / content | ❌ Missing | — |

---

## Remaining Critical Issues

### C1. Broken /privacy and /terms links (404)
Footer links to Privacy Policy and Terms of Service both return 404. This is a trust failure for users, AI E-E-A-T evaluators, and potentially a GDPR violation (EUR pricing = EU jurisdiction).

**Fix:** Publish real Privacy Policy and Terms of Service pages. Add to sitemap.ts once live.

---

## High Priority Issues

### H1. No og:image
OG title/description are set, but no image. Link previews on LinkedIn, Slack, X show no visual.

**Fix:** Create a 1200×630 PNG and add via Next.js metadata:
```tsx
openGraph: {
  images: [{ url: 'https://hrbreaker.co/og-image.png', width: 1200, height: 630 }],
}
```

### H2. No /about page — zero E-E-A-T entity signals
No identifiable person or team behind the product. AI trust systems cannot verify who operates HR-Breaker.

### H3. Organization.sameAs is empty
The JSON-LD has `"sameAs": []` — no linked social profiles. This means Google and AI systems can't cross-reference the entity.

**Fix:** Create LinkedIn Company Page + X/Twitter, then populate sameAs:
```json
"sameAs": [
  "https://www.linkedin.com/company/hrbreaker",
  "https://twitter.com/hrbreaker"
]
```

### H4. Job Hunter and Offer Mode offers missing "price"
Two of three Offer objects have no `price` field. Google may not generate rich results for incomplete Offer data.

**Fix:** Add `"price": "20"` for Job Hunter and the actual price for Offer Mode.

### H5. No favicon
`/favicon.ico` returns 404.

### H6. FAQ answers still not in visible SSR HTML
The 5 FAQ answers exist in JSON-LD (good for schema), but the visible page text still only shows question headings — answers hydrate client-side. For maximum citability, the answers should also be in the rendered HTML.

---

## Medium Priority Issues

### M1. No images on page (0 `<img>` tags)
### M2. No blog or content surface
### M3. No testimonials or social proof
### M4. EUR pricing but no localization
### M5. No Organization logo in schema
### M6. H1 opacity:0 inline animation style

---

## Category Deep Dives

### AI Citability — 35/100 (was 32, +3)

The FAQ answers are now machine-readable via FAQPage schema — AI systems can extract them directly without parsing page text. This lifts citability for question-answering use cases. However, the visible page content is still thin (~330 words), with no statistics, no comparison tables, and no in-depth explanations.

**What would move this to 50+:**
- Server-render FAQ answers in visible HTML (+5)
- Add a hero statistic with source citation (+3)
- Add a comparison table: manual vs. HR-Breaker optimization (+5)
- Publish 3 blog posts on ATS topics (+10)

### Brand Authority — 10/100 (unchanged)

No external signals anywhere. The Organization schema has `sameAs: []` which explicitly signals no cross-platform presence. Until LinkedIn, X/Twitter, Product Hunt, or YouTube exist and are linked, this stays near zero.

### Content E-E-A-T — 15/100 (unchanged)

Still no author, no about page, broken legal pages. The Organization schema provides a description but no credentials, no team, no address.

### Technical GEO — 72/100 (was 70, +2)

Mature technical foundation. JSON-LD properly embedded and valid. All core GEO files deployed. Remaining gaps: og:image, favicon, broken legal links.

**Deployed:** robots.txt ✅, sitemap.xml ✅, llms.txt ✅, canonical ✅, OG ✅, Twitter ✅, robots meta ✅, JSON-LD ✅, SSR ✅, HTTPS+HSTS ✅, CSP ✅
**Missing:** og:image ❌, favicon ❌, /privacy 404 ❌, /terms 404 ❌

### Schema & Structured Data — 62/100 (was 0, +62)

**Now deployed:**
- ✅ Organization (@id, name, url, description)
- ✅ SoftwareApplication (category, OS, description, 3 Offers)
- ✅ FAQPage (5 Questions with Answers)
- ✅ JSON-LD on both / and /pricing pages

**Gaps preventing 80+:**
- ⚠️ sameAs empty (no social links)
- ⚠️ 2 of 3 Offers missing price
- ⚠️ No Organization logo
- ⚠️ No BreadcrumbList schema
- ⚠️ No WebSite + SearchAction schema

### Platform Optimization — 12/100 (unchanged)

No active presence on any platform AI models train on or cite.

---

## Quick Wins (This Week)

1. **Ship /privacy + /terms** — fixes broken links + GDPR + E-E-A-T (+5-8 composite pts)
2. **Add og:image** — 1200×630 share image (+2 pts, major UX improvement for sharing)
3. **Add favicon** — trivial fix, noticeable gap (+1 pt)
4. **Fill missing Offer prices** in JSON-LD (+2 Schema pts)
5. **Server-render FAQ answers** in visible HTML (+3-5 Citability pts)

**Expected score after these 5 fixes: 32 → ~42 (exit Critical into Poor tier)**

---

## 30-Day Action Plan

### Week 1: Schema + Legal ← YOU ARE HERE
- [x] ~~robots.txt~~ ✅
- [x] ~~sitemap.xml~~ ✅
- [x] ~~llms.txt~~ ✅
- [x] ~~Title + meta description optimization~~ ✅
- [x] ~~Canonical URLs~~ ✅
- [x] ~~OG + Twitter Card meta~~ ✅
- [x] ~~JSON-LD (Organization + SoftwareApplication + FAQPage)~~ ✅
- [ ] Ship /privacy + /terms pages
- [ ] Add og:image
- [ ] Add favicon
- [ ] Fill missing Offer prices in JSON-LD
- [ ] Server-render FAQ answers in HTML
- [ ] Add Organization logo to schema

### Week 2: Trust & Content (target: 50/100)
- [ ] Publish /about with founder bio, photo, LinkedIn
- [ ] Create LinkedIn Company Page + X/Twitter
- [ ] Populate Organization.sameAs with social URLs
- [ ] Publish /how-it-works explaining hallucination detection
- [ ] Add 2-3 product screenshots with alt text
- [ ] Add 1 hero statistic with credible source

### Week 3: Brand Authority (target: 60/100)
- [ ] Product Hunt launch
- [ ] YouTube demo (2-3 min)
- [ ] Collect 5 testimonials with real names
- [ ] First blog post: "How ATS Keyword Matching Works"
- [ ] Add Article schema to blog

### Week 4: Content Engine (target: 70/100)
- [ ] 2 more blog posts (ATS topics)
- [ ] Add BreadcrumbList + WebSite schema
- [ ] Submit sitemap to Google Search Console + Bing
- [ ] Set up brand mention monitoring
- [ ] Re-audit: target 70/100

---

## Appendix: JSON-LD Validation

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",           // ✅ Valid
      "@id": "https://hrbreaker.co/#org", // ✅ Good practice
      "name": "HR-Breaker",              // ✅
      "url": "https://hrbreaker.co/",    // ✅
      "description": "...",              // ✅
      "sameAs": []                       // ⚠️ Empty — populate when social profiles exist
    },
    {
      "@type": "SoftwareApplication",    // ✅ Valid
      "applicationCategory": "BusinessApplication", // ✅
      "offers": [
        { "name": "Starter", "price": "0", "priceCurrency": "EUR" },  // ✅ Complete
        { "name": "Job Hunter", "priceCurrency": "EUR" },              // ⚠️ Missing price
        { "name": "Offer Mode", "priceCurrency": "EUR" }               // ⚠️ Missing price
      ]
    },
    {
      "@type": "FAQPage",               // ✅ Valid
      "mainEntity": [5 Questions]        // ✅ All have acceptedAnswer
    }
  ]
}
```

**Verdict:** Valid and well-structured. Fix the 2 missing prices and add sameAs values to reach Schema 75+.

## Appendix: Pages Analyzed

| URL | Status | Title | Schema | Key Issues |
|---|---|---|---|---|
| / | 200 | HR-Breaker — ATS Resume Optimization... | Org + SoftwareApp + FAQ ✅ | No og:image, FAQ client-only |
| /pricing | 200 | Pricing — Free, Job Hunter... | Has JSON-LD ✅ | Missing Offer prices |
| /robots.txt | 200 ✅ | — | — | Excellent |
| /sitemap.xml | 200 ✅ | — | — | Good (2 URLs) |
| /llms.txt | 200 ✅ | — | — | Comprehensive |
| /privacy | 404 ❌ | — | — | Critical: broken link |
| /terms | 404 ❌ | — | — | Critical: broken link |
| /about | 404 | — | — | High: missing |
| /favicon.ico | 404 | — | — | High: missing |

---

**Score trajectory: 20 → 22 → 25 → 32. Next target: 42 (exit Critical). Requires: /privacy + /terms + og:image + FAQ SSR.**
