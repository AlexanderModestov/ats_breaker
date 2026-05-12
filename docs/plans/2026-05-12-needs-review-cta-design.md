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

- No change to PATCH endpoint logic or `useUpdateOptimizationJob` hook semantics.
- No change to copy on already-parsed fields.
- No editing flow on the optimization start page (the design doc `2026-05-10-job-parsing-manual-fix-design.md` explicitly rejects pre-optimization confirmation).

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

### Results page (`results/[id]/page.tsx`)

- Add `Plus` to lucide-react import.
- Replace the two muted `<button>` blocks for title and company with the new dashed amber buttons per the spec above.
- Leave `<Building2 />`, save flow, and the edit/loading/resolved branches untouched.

### History cards (`components/OptimizationCard.tsx`)

Same affordance plumbed into the list:

- Backend: `OptimizationSummary` gains `needs_review: list[str] = []`, populated from `job_parsed.get("needs_review")` in `list_optimization_runs`.
- Frontend types: `OptimizationSummary.needs_review?: string[]`.
- `InlineEdit` extracted from the results page to `components/InlineEdit.tsx` for reuse. Its input now also `stopPropagation`s on click so card-level navigation does not fire while editing.
- Card uses `useUpdateOptimizationJob(opt.id)` — already invalidates `["optimizations"]`, so the list refreshes after save. Local `setLocalOpt` mirrors the results-page pattern to avoid a flicker between save and refetch.
- Card's own `onClick` is suppressed while `editing !== null` so blur/save events do not navigate to the result page.
- All interactive elements inside the card (CTA buttons, input, delete button) `stopPropagation` on click.

### Sizing

- Card title CTA uses the same compact spec as the company CTA (border 1px, `text-base font-medium`, h-3.5 Plus) — fits inside `<CardTitle>` without breaking the 1-line clamp.
- Card company CTA matches results-page company CTA exactly.

Estimated diff: ~80 LOC across 5 files.

## Edge cases

- Both fields in `needs_review` → two stacked buttons (different DOM nodes already).
- `!job` (parsing in flight) → existing `"Optimization in Progress"` h1 wins; no buttons.
- Old runs without `needs_review` → empty set, no buttons; renders as plain title/company (or `"Untitled Job"` / `"Unknown Company"` on cards as before).
- Editing on a card while another card is also in edit mode: each card holds its own state — no interference.
- Click outside an editing input while typing → `onBlur` cancels the edit without saving; the input does not propagate the click to the card, so no accidental navigation.

## Manual verification

1. Trigger an optimization on a URL the parser can't fully resolve (so `needs_review` ends up non-empty).
2. On `/results/[id]`:
   - Amber dashed button visible in the h1 slot and/or meta-line.
   - Hover → solid border + amber-50 background.
   - Tab to it → amber focus ring.
   - Click → `InlineEdit` input, type value, Enter → button replaced by plain text.
   - Reload page → field persists as plain text (no amber).
3. On `/history`:
   - Same amber CTA on the corresponding card.
   - Click does not navigate to the result page; input takes focus instead.
   - Save → card updates in place; navigating into the card now shows the corrected value.
4. Toggle dark mode, repeat.
