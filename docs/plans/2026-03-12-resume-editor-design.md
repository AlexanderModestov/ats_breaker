# Resume Editor — Post-Generation Editing

**Date:** 2026-03-12

## Overview

After resume optimization completes, user can review and edit the resume before downloading PDF. Two editing modes: direct HTML editing (Monaco) and text instructions to LLM. A requirements checklist shows which job requirements are covered.

## API Endpoints

Three new endpoints on top of existing `/api/optimize/{id}`:

### `GET /api/optimize/{id}/requirements`

Returns checklist of job requirements with coverage status.

```json
{
  "requirements": [
    {"id": "req_1", "text": "3+ years Python", "covered": true},
    {"id": "req_2", "text": "Experience with Kubernetes", "covered": false},
    {"id": "req_3", "text": "CI/CD pipelines", "covered": false}
  ]
}
```

Built from parsed `JobPosting` (requirements + keywords), matched against current HTML via keyword text search. No LLM call needed.

### `POST /api/optimize/{id}/edit`

Applies LLM instruction via patches.

```json
// Request
{"instruction": "Add Kubernetes experience from my previous role"}
// Response
{
  "patches": [
    {"selector": "#experience-item-2", "action": "append", "html": "<li>Managed Kubernetes clusters...</li>"}
  ],
  "updated_html": "...full html fallback..."
}
```

Backend returns both patches and full HTML as fallback.

### `POST /api/optimize/{id}/validate`

Lightweight validation (no expensive LLM filters).

```json
// Request
{"html": "...current html..."}
// Response
{
  "results": [
    {"filter": "KeywordMatcher", "score": 0.82, "passed": true},
    {"filter": "ContentLengthChecker", "score": 1.0, "passed": true}
  ],
  "requirements": ["...updated checklist..."]
}
```

Filters used: `ContentLengthChecker` (1 page check) and `KeywordMatcher` (TF-IDF keyword coverage).

## LLM Agent: `resume_editor`

Lightweight Pydantic-AI agent on flash model. Receives:
- Current HTML resume
- Original user resume (to prevent hallucination)
- Instruction (free text or "Add requirement: {text}")

Returns:

```python
class ResumePatch(BaseModel):
    selector: str          # CSS selector (e.g. "#skills-list", "#experience-item-1 ul")
    action: Literal["replace", "append", "prepend", "remove"]
    html: str | None       # new HTML content (None for remove)

class EditResult(BaseModel):
    patches: list[ResumePatch]
    reasoning: str         # brief explanation of changes
```

### HTML ID Convention

Resume HTML template must use predictable id attributes: `#summary`, `#experience`, `#experience-item-0`, `#skills-list`, `#education`. Added as requirement in optimizer prompt.

### Server-side Patch Application

Backend always applies patches itself via BeautifulSoup and stores current HTML in session. Ensures consistency even if frontend patch application fails.

## Frontend Layout

Three-panel layout:

### Left Panel — Requirements Checklist
- List from `GET /requirements`
- Covered = green check, uncovered = red cross
- Click on uncovered requirement → sends instruction to `/edit` ("Add requirement: {text}")
- User can edit instruction before sending

### Center — Resume Preview
- HTML rendered in iframe
- Changed blocks highlighted (yellow, 3s fade)
- Toggle: "Preview" / "Code" (Monaco editor with HTML)

### Bottom Panel — Instruction Bar
- Chat-style text input for free-form instructions
- "Apply" button → calls `/edit` → patches applied → preview updated → `/validate` runs

### Flow
1. User makes change (code / instruction / click requirement)
2. Preview updates
3. `/validate` runs automatically (1s debounce for manual edits)
4. Checklist and scores update
5. "Download PDF" button renders final HTML to PDF

## Error Handling

**Patch selector not found** — Backend logs warning, returns `updated_html` with patches that did apply. Frontend shows toast: "Some changes applied differently than expected", updates preview from `updated_html`.

**Invalid HTML from code editor** — `/validate` returns error from `DataValidator`. Frontend shows error, doesn't update preview. Previous working version preserved on server.

**Resume exceeds 1 page** — `ContentLengthChecker` returns `passed: false`. Frontend shows warning near Download button.

**Manual edits + LLM patches conflict** — No conflict. Frontend sends current HTML with instruction to `/edit`. LLM always sees latest state.

**Undo** — Frontend stores HTML version history (array of strings). Undo button reverts to previous version. Client-side only.

## Validation Strategy

Only lightweight filters run during editing:
- `ContentLengthChecker` (priority 0) — page size check
- `KeywordMatcher` (priority 4) — TF-IDF keyword matching

Expensive filters (LLMChecker, HallucinationChecker, VectorSimilarity, AIGenerated) are NOT run — too slow and costly for interactive editing.
