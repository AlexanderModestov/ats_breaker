# UI Redesign — Option B: Light with Dark Hero Sections

**Date:** 2026-05-25
**Scope:** Landing page, app (optimize), pricing, auth screens
**Aesthetic direction:** Linear / Clerk / Resend — minimal, professional, sharp typographic hierarchy

---

## Design System

### Typography
- **Font:** Geist Sans (replace Satoshi)
- **Headings:** `font-weight: 700–800`, `letter-spacing: -0.03em`
- **Body:** regular weight, readable

### Color Tokens

| Token | Light mode | Dark sections |
|---|---|---|
| Background | `#FFFFFF` | `#09090B` (zinc-950) |
| Foreground | `#18181B` (zinc-900) | `#FAFAFA` |
| Muted text | `#71717A` (zinc-500) | `#A1A1AA` (zinc-400) |
| Brand accent | `#7C3AED` (violet-700) | same |
| Border | `#E4E4E7` (zinc-200) | `#27272A` (zinc-800) |
| Card | `#FAFAFA` | `#18181B` (zinc-900) |

### Spacing & Shape
- Border radius: `0.5rem` (down from 0.75rem — crisper)
- No box shadows — borders only (`1px solid var(--border)`)
- Generous section whitespace

### Motion
- Keep Framer Motion, reduce usage
- Page enter: fade + 8px slide up
- Modal appear: scale from 0.97
- No word/list-item stagger animations

---

## Landing Page

### Hero (dark section)
- Full-viewport, `#09090B` background
- Headline (2 lines, `text-5xl–6xl font-bold tracking-tight`):
  ```
  Transform your resume
  for every job posting.
  ```
- Subline: *"AI-powered. ATS-ready. One click."* — zinc-400, `text-lg`
- CTAs: filled violet "Get started free" + ghost "See how it works" (smooth scroll)
- Background: subtle radial violet bloom at ~15% opacity — no imagery

### Light sections (white, `max-w-5xl` centered)
1. **How it works** — 3 numbered steps horizontal. Large zinc-200 step numbers, bold title, short description.
2. **Features** — 2×3 grid. White cards, zinc-200 border, icon + title + one sentence. No fills.
3. **Pricing** — 3 cards. Middle card gets `1px violet-400 border` + `bg-violet-50`. No ribbons or badges.

### Header
- Transparent over hero → white/blurred sticky on scroll
- Logo + nav links + "Sign in" ghost + "Get started" filled violet

### Footer
- Dark (`#09090B`), logo left, sparse links right, muted legal text bottom

---

## Auth Screens

### Layout
- Full-page centered card
- Background: zinc-50 + fine CSS dot-grid (zinc-200 dots, 1px, 20px spacing)
- Card: white, `1px` zinc-200 border, `0.5rem` radius, `max-w-sm`

### Sign-in card (top to bottom)
1. Logo mark + wordmark, centered
2. Heading: **"Welcome back"** — `text-2xl font-bold tracking-tight`
3. Subtext: *"Sign in to continue optimizing your resume."* — zinc-500
4. "Continue with Google" — full width, white bg, zinc-200 border, Google logo left
5. Fine-print: *"By continuing, you agree to our Terms and Privacy Policy."*

### Sign-up card
- Same structure, heading: **"Create your account"**

### Removed
- Split-layout (left branding panel + right form) — dropped entirely

---

## App — Core Tool (Optimize Page)

### Navigation
- **Desktop:** Slim sidebar (`w-56`)
  - Logo at top
  - Nav items: Optimize, CVs, Coach, History — active state: filled violet left-border indicator
  - User section pinned at bottom: avatar/name, settings icon, logout
- **Mobile:** Bottom tab bar

### Main work area
- White canvas, `max-w-2xl` centered, generous vertical padding
- **CV section:** label `text-sm font-medium text-zinc-500` "Your resume", CV dropdown below
- **Job posting section:** label "Job posting", expanding textarea, zinc-200 border
- No decorative icons inside input fields

### Optimize button
- Full width of `max-w-2xl`, filled violet, `font-medium`
- Loading state: disabled + subtle shimmer (no spinner icon)

### Quota banner
- Slim bar above button (free tier only)
- `bg-zinc-100 text-zinc-600 text-sm`
- "3 optimizations left this week. [Upgrade →]" — upgrade link is violet
- No alert icons, no red

### Post-optimization
- Results appear below the button in same column (no modal, no new page)
- Resume preview card: fade-up entry

---

## Pricing Page & Modal

### Standalone page
- White, `max-w-4xl` centered
- Violet eyebrow label: `text-xs font-semibold uppercase tracking-widest text-violet-600` — "Pricing"
- Heading: **"Simple, transparent pricing."** — `text-4xl font-bold tracking-tight`
- Subline: *"Start free. Upgrade when you're ready."*

### Cards
| Plan | Treatment |
|---|---|
| Free | Standard zinc-200 border |
| Job Hunter | `1px violet-400 border` + `bg-violet-50` |
| Offer Mode | Standard zinc-200 border |

Each card: plan name `font-semibold`, price `text-4xl font-bold`, billing cadence muted, feature list with zinc checkmarks, CTA button at bottom.

### Pricing modal (in-app)
- Dialog, `max-w-3xl`, white
- Header: "Upgrade your plan" + close button
- Overlay: `bg-black/60` (no backdrop blur)
- Same three cards inside

### Upgrade confirmation
- Secondary `max-w-sm` dialog over pricing modal
- Shows prorated cost
- "Confirm upgrade" (filled violet) + "Cancel" (ghost)

### Removed
- Animated gradients, "Most Popular" ribbon badges, glow effects
