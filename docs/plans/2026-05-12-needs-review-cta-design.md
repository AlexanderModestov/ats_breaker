# Visible CTA for Unparsed Title/Company — Design

**Date:** 2026-05-12
**Status:** Approved, ready for implementation

## Problem

On the results page (`/results/[id]`), when the parser fails to extract `title` and/or `company`, the user sees a muted italic placeholder:

> *Position not detected — click to set*  ✎

Visually it blends with secondary text — users scroll past without realizing the field is editable. The affordance is technically present but not discoverable. Builds on the work in `2026-05-10-job-parsing-manual-fix-design.md`, which introduced the `needs_review` mechanism and the edit endpoint; this design only changes the visual treatment of the placeholder.

## Goal

Make "this field needs your input" obviously interactive at a glance, without restructuring the page layout or adding banners that decouple the notice from the action target.

## Non-goals

- No change to backend (`needs_review` flow, PATCH endpoint).
- No change to `InlineEdit` component, save flow, or `useUpdateOptimizationJob` hook.
- No change to history list (`OptimizationCard.tsx`) — separate task; see "Future work".
- No change to copy on already-parsed fields.

## Design

Replace the current muted italic placeholder with a **dashed-border action button** in amber tone. Pattern is widely recognized (Notion "+ Add property", Linear "+ Add label") and reads as a clear CTA.

### Visual spec

**Title (h1 slot):**

- `border: 2px dashed amber-400`
- `text: amber-700`, `font-bold`, `text-2xl sm:text-3xl` (matches h1 size, prevents layout shift)
- `padding: px-3 py-1`, `rounded-lg`
- `<Plus />` icon (h-5 w-5) left of the label
- Label: **"Add position"**

**Company (meta-line slot):**

- `border: 1px dashed amber-400`
- `text: amber-700`, `font-medium`, `text-sm`
- `padding: px-2 py-0.5`, `rounded-md`
- `<Plus />` icon (h-3.5 w-3.5)
- Label: **"Add company"**
- `<Building2 />` icon stays outside the button, in default muted color — preserves the meta-line rhythm.

### States

| State    | Treatment                                                                                  |
|----------|--------------------------------------------------------------------------------------------|
| Default  | dashed border, amber text                                                                  |
| Hover    | `bg-amber-50`, border becomes solid (`hover:border-solid`)                                 |
| Focus    | `ring-2 ring-amber-400` via `focus-visible`                                                |
| Editing  | unchanged — existing `InlineEdit` input renders in place                                   |
| Resolved | button replaced by plain text (`job.title` / `job.company`), no amber styling              |

### Dark mode

- `dark:border-amber-500/60`
- `dark:text-amber-400`
- `dark:hover:bg-amber-950/30`

### Copy

| Before                                  | After          |
|-----------------------------------------|----------------|
| Position not detected — click to set    | + Add position |
| Company not detected — click to set     | + Add company  |

Rationale: short, action-oriented; the dashed border + Plus icon communicates "missing, fill me in" without needing descriptive prose.

## Accessibility

- Affordance does not rely on color alone (dashed border + `Plus` icon).
- `aria-hidden="true"` on icons; button text is self-sufficient for screen readers.
- `focus-visible:ring-2 ring-amber-400` for keyboard navigation.
- `amber-700` on `white` / `amber-50` passes WCAG AA for normal text. Dark-mode `amber-400` on dark surfaces also passes.

## Implementation

Single file: `frontend/src/app/(protected)/results/[id]/page.tsx`.

- Add `Plus` to lucide-react import.
- Replace the two `<button>` blocks (current lines 67-74 for title and 91-99 for company) with the new dashed amber buttons per the spec above.
- Leave `<Building2 />`, `InlineEdit`, `saveField`, all hooks, and the edit/loading/resolved branches untouched.

Estimated diff: ~15 JSX/Tailwind lines.

## Edge cases

- Both fields in `needs_review` → two stacked buttons (different DOM nodes already).
- `!job` (parsing in flight) → existing `"Optimization in Progress"` h1 wins; no buttons.
- Old runs without `needs_review` → `new Set([])`, no buttons; renders as plain title/company.

## Manual verification

1. Trigger an optimization on a URL the parser can't fully resolve (so `needs_review` ends up non-empty).
2. On `/results/[id]`:
   - Amber dashed button visible in the h1 slot and/or meta-line.
   - Hover → solid border + amber-50 background.
   - Tab to it → amber focus ring.
   - Click → `InlineEdit` input, type value, Enter → button replaced by plain text.
   - Reload page → field persists as plain text (no amber).
3. Toggle dark mode, repeat.

## Future work

`OptimizationCard.tsx` in the history list still shows static `"Untitled Job"` / `"Unknown Company"`. Plumb `needs_review` through `OptimizationSummary` and apply the same amber CTA on cards. Out of scope for this change.
