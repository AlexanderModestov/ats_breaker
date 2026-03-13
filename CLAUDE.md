# CLAUDE.md

# HR-Breaker

Tool for optimizing resumes for job postings and passing automated filters.

## How it works

1. User uploads resume in ANY text format (LaTeX, plain text, markdown, HTML) - content source only
2. User provides job posting URL or text description
3. LLM extracts content from resume and generates NEW HTML resume that:
   - Maximally fits the job posting
   - Follows guidelines: one-page PDF, no misinformation, etc.
4. System runs internal filters (LLM-based ATS simulation, keyword matching, hallucination detection, etc.)
5. If filters reject, repeat from step 3 using feedback
6. When all checks pass, render HTML→PDF via WeasyPrint and return

## Architecture

1. Next.js frontend + FastAPI backend
2. Pydantic-AI LLM agent framework
3. Google Gemini models (configurable via env)
4. Modular filter system - easy to add new checks
5. Resume caching - input once, apply to many jobs

Python: 3.10+
Package manager: uv
Always use venv: `source .venv/bin/activate`
Unit-tests: pytest
HTTP library: httpx

Pydantic-AI docs: https://ai.pydantic.dev/llms-full.txt

## Guidelines

When debugging use 1-2 iterations only (costs money). Use these settings:
```
GEMINI_THINKING_BUDGET=1024
GEMINI_PRO_MODEL=gemini-2.5-flash
GEMINI_FLASH_MODEL=gemini-2.5-flash
```

## Current Implementation

### Structure
```
src/hr_breaker/
├── models/          # Pydantic data models
├── agents/          # Pydantic-AI agents
├── filters/         # Plugin-based filter system
├── services/        # Rendering, scraping, caching
│   └── scrapers/    # Job scraper implementations
├── utils/           # Helpers
├── orchestration.py # Core optimization loop
├── api/             # FastAPI backend
├── cli.py           # Click CLI
└── config.py        # Settings
```

### Agents
- `job_parser` - Parse job posting → title, company, requirements, keywords
- `optimizer` - Generate optimized HTML resume from source + job
- `combined_reviewer` - Vision + ATS screening in single LLM call
- `name_extractor` - Extract name from any resume format
- `hallucination_detector` - Detect fabricated content
- `ai_generated_detector` - Detect AI-generated content indicators

### Filter System
Filters run by priority (lower first). Default: parallel execution. Use `--seq` for early exit on failure.

| Priority | Filter | Purpose |
|----------|--------|---------|
| 0 | ContentLengthChecker | Pre-render size check (≤1 page) |
| 1 | DataValidator | Validate HTML structure |
| 3 | HallucinationChecker | Detect fabrications |
| 4 | KeywordMatcher | TF-IDF keyword matching |
| 5 | LLMChecker | Combined vision + ATS simulation |
| 6 | VectorSimilarityMatcher | Sentence-transformer similarity |
| 7 | AIGeneratedChecker | AI content detection |

To add filter: subclass `BaseFilter`, set `name` and `priority`, use `@FilterRegistry.register`

### Services
- `renderer.py` - HTMLRenderer (WeasyPrint)
- `job_scraper.py` - Scrape job URLs (httpx → Wayback → Playwright fallback)
- `pdf_parser.py` - Extract text from PDF
- `cache.py` - Resume caching
- `pdf_storage.py` - Save/list generated PDFs
- `length_estimator.py` - Content length estimation for resume sizing

### Commands
```bash
# CLI
uv run hr-breaker optimize resume.txt https://example.com/job
uv run hr-breaker optimize resume.txt job.txt -d              # debug mode
uv run hr-breaker optimize resume.txt job.txt --seq           # sequential filters (early exit)
uv run hr-breaker list                                        # list generated PDFs

# Tests
uv run pytest tests/
```

### Output
- Final PDFs: `output/<name>_<company>_<role>.pdf`
- Debug iterations: `output/debug_<company>_<role>/` (with -d flag)
- Records: `output/index.json`

### Resume Rendering
- LLM generates HTML body → WeasyPrint renders to PDF
- Templates in `templates/` (resume_wrapper.html, resume_guide.md)
- Name extraction uses LLM - handles any input format
