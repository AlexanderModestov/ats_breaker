# Coach Mobile Responsive — Design

**Date:** 2026-04-28
**Scope:** Eliminate horizontal scroll on protected pages (especially `/coach`) on mobile viewports, and stack the coach header on small screens.

## Problem

User report: opening `/coach` on mobile produces horizontal scroll; the page must be scrolled left/right to see all content.

### Root cause

Not the coach page itself — it's the `Navbar` (`frontend/src/components/Navbar.tsx`). Width budget on a 360–375px viewport:

| Element | Width |
|---------|-------|
| `px-4` outer padding (left+right) | 32px |
| Logo: HR badge + gap + "Breaker" wordmark | ~125px |
| Nav: 4 icon buttons + gaps | ~164px |
| User section: Settings + divider + LogOut icons | ~97px |
| **Total** | **~386px** |

`justify-between` distributes free space but does not shrink children below their content width. When their sum exceeds the viewport, the container overflows horizontally — visible on every protected page, but the user noticed it on `/coach`.

### Secondary issues

- **Coach header (`coach/page.tsx`)** — `<select>` and the Chat/Storybank tab switcher share one `flex justify-between` row. Cramped on narrow screens (B-class issue from initial triage). Not the cause of horizontal scroll, but worth fixing alongside.
- **Chat bubble (`CoachChat.tsx`)** — `max-w-[80%]` exists, but no `break-words`. Long URLs/words will eventually stretch the bubble. Pre-emptive 1-line fix to avoid regression.

## Decision: minimal three-line fix

Three independent surgical changes. Per CLAUDE.md "Surgical Changes" principle.

### 1. Navbar — hide "Breaker" wordmark on mobile

`frontend/src/components/Navbar.tsx:43-45`

```tsx
<span className="hidden text-lg font-semibold tracking-tight sm:inline">
  Breaker
</span>
```

Saves ~85px. HR badge remains as the brand mark on mobile. Wordmark returns at `sm` breakpoint (≥640px).

**Alternatives considered:**
- Reduce padding on nav buttons → `size="sm"` is already minimum.
- Move user-section into a menu → over-engineering for a one-line problem.

### 2. Coach header — stack on mobile

`frontend/src/app/(protected)/coach/page.tsx:74`

```tsx
<div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
```

On mobile: select on its own row (full width), tabs below. On `sm+`: original single-row layout. `<select>`'s `flex-1 max-w-md` and tab switcher's `shrink-0` are unchanged — they continue to behave correctly in both layouts.

### 3. Bubble break-words

`frontend/src/components/CoachChat.tsx:35` — append `break-words` to the bubble className. Tailwind `break-words` maps to `overflow-wrap: break-word`. Long unbroken strings wrap inside the bubble instead of stretching it.

## Verification

No frontend test runner exists (consistent with the iOS OAuth fix decision). Verification is manual.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | All protected pages at 360px viewport (DevTools) | No horizontal scroll |
| 2 | Resize across `sm` breakpoint (640px) | "Breaker" wordmark appears at sm+, disappears below |
| 3 | `/coach` at 360px | Select on top, tabs on bottom; no overlap; badge inside tab pill |
| 4 | `/coach` at ≥640px | Original single-row header; no regression |
| 5 | Chat with very long URL | Bubble wraps, no horizontal scroll |

## Out of scope (deferred — YAGNI)

- Telegram WebApp `viewportStableHeight` integration for keyboard handling — wait for an actual report.
- `overflow-x-hidden` on body as safety net — fix root cause first.
- Hamburger menu / nav redesign — current four icons fit fine after wordmark hide.
- Touch-target audit — separate accessibility pass, not the current complaint.

## Files touched

- `frontend/src/components/Navbar.tsx` (1 line)
- `frontend/src/app/(protected)/coach/page.tsx` (1 line)
- `frontend/src/components/CoachChat.tsx` (1 line)

No backend changes. No new dependencies.
