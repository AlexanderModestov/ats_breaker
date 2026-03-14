# Resume Editor Simplification — Design

**Date:** 2026-03-14
**Goal:** Simplify the resume editor by removing the code view and adding inline double-click editing.

## Core Experience

The editor page has two panels: a requirements checklist on the left, and a resume preview on the right with an AI instruction bar at the bottom.

The preview shows the resume as it will look in the final PDF. Users can make changes two ways:

1. **Double-click** any text block in the preview to open a small floating popup with a plain text area and Save/Cancel buttons. For quick, direct edits.

2. **AI instruction bar** at the bottom for structural or strategic changes ("reorder experience to lead with backend roles", "add more about leadership"). Also triggered by clicking uncovered requirements in the checklist.

No code view, no Monaco editor, no HTML exposed to the user.

## Double-Click Popup Editing

- User double-clicks a text element (paragraph, list item, heading) in the preview iframe
- A floating popup appears near the clicked element with:
  - A plain `<textarea>` pre-filled with the element's text content
  - Save and Cancel buttons
- On Save: the text change is converted to a `ResumePatch` (replace action) and applied via `apply_patches` on the backend
- On Cancel: popup closes, no changes
- Undo/redo still works — each save pushes to the history stack

### What's Editable

- Paragraphs, list items, headings, spans with text content
- NOT editable: layout containers, section headers (like "EXPERIENCE"), the header/contact line

### Preview Iframe Communication

- Inject a script into the iframe's `srcDoc` that listens for `dblclick` events
- On double-click, post a message to the parent with the element's text, bounding rect, and a CSS selector path
- Parent renders the popup positioned near the element
- On save, parent sends the updated text back as a patch

## What Changes From Current Implementation

### Remove
- Monaco editor and `@monaco-editor/react` dependency
- Code/Preview toggle button in the toolbar
- The `mode` state ("preview" | "code")

### Keep As-Is
- Requirements checklist (left panel)
- AI instruction bar (bottom)
- Undo/Redo buttons
- PDF download button
- `useResumeEditor` hook (history, validation, LLM edit mutation)
- All backend endpoints unchanged

### Add
- `EditPopup` component — floating textarea with Save/Cancel, positioned relative to clicked element
- Iframe script injection for double-click detection and `postMessage` communication
- New `applyTextEdit` function in the hook — takes selector + new text, creates a patch, calls backend to apply

### Architecture
All edits (both manual and AI) go through the patch system. Direct text edits skip the LLM and create a simple replace patch client-side.
