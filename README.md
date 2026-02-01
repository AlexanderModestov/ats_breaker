# HR-Breaker

Resume optimization tool that transforms any resume into a job-specific, ATS-friendly PDF.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)

## Features

- **Any format in** - LaTeX, plain text, markdown, HTML, PDF
- **Optimized PDF out** - Single-page, professionally formatted
- **LLM-powered optimization** - Tailors content to job requirements
- **Minimal changes** - Preserves your content, only restructures for fit
- **No fabrication** - Hallucination detection prevents made-up claims
- **Opinionated formatting** - Follows proven resume guidelines (one page, no fluff, etc.)
- **Multi-filter validation** - ATS simulation, keyword matching, structure checks
- **Modern Web UI** - Next.js frontend with Supabase authentication
- **CLI support** - Command-line interface for power users
- **Debug mode** - Inspect optimization iterations

## How It Works

1. Upload resume in any text format (content source only)
2. Provide job posting URL or text description
3. LLM extracts content and generates optimized HTML resume
4. System runs internal filters (ATS simulation, keyword matching, hallucination detection)
5. If filters reject, regenerates using feedback
6. When all checks pass, renders HTML→PDF via WeasyPrint

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- [uv](https://github.com/astral-sh/uv) package manager
- Supabase project (for web UI)
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/btseytlin/hr-breaker.git
cd hr-breaker

# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && npm install && cd ..

# Configure environment
cp .env.example .env
cp frontend/.env.example frontend/.env.local
# Edit both files with your API keys and Supabase credentials
```

### Running the Application

**API Server:**
```bash
./scripts/run-api.sh
# Or manually: uv run uvicorn hr_breaker.api.main:app --reload
```

**Frontend:**
```bash
./scripts/run-frontend.sh
# Or manually: cd frontend && npm run dev
```

The frontend runs at http://localhost:3000 and the API at http://localhost:8000.

## Usage

### Web UI

1. Sign in with Google
2. Upload your resume (PDF, TXT, TEX, MD)
3. Enter job posting URL or paste description
4. Click "Start Optimization"
5. Download your optimized PDF

### CLI

```bash
# From URL
uv run hr-breaker optimize resume.txt https://example.com/job

# From job description file
uv run hr-breaker optimize resume.txt job.txt

# Debug mode (saves iterations)
uv run hr-breaker optimize resume.txt -d

# List generated PDFs
uv run hr-breaker list
```

## Output

- Final PDFs: `output/<name>_<company>_<role>.pdf`
- Debug iterations: `output/debug_<company>_<role>/`
- Records: `output/index.json`

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key |
| `SUPABASE_URL` | Yes (web) | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes (web) | Supabase anonymous key |
| `SUPABASE_SERVICE_KEY` | Yes (web) | Supabase service role key |
| `SUPABASE_JWT_SECRET` | Yes (web) | Supabase JWT secret |
| `API_CORS_ORIGINS` | No | Allowed CORS origins (default: http://localhost:3000) |

For the frontend, copy `frontend/.env.example` to `frontend/.env.local`:

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anonymous key |
| `NEXT_PUBLIC_API_URL` | No | API URL (default: http://localhost:8000/api) |

See `.env.example` for all available options (filter thresholds, scraper settings, etc.)

### Supabase Setup

1. Create a new Supabase project
2. Run the migrations in `supabase/migrations/` in order
3. Enable Google OAuth in Authentication → Providers
4. Create storage buckets: `cvs` and `results`

---

## Architecture

```
src/hr_breaker/
├── api/             # FastAPI backend
│   ├── routes/      # API endpoints (cvs, optimize, users)
│   ├── auth.py      # JWT verification
│   ├── deps.py      # Dependency injection
│   └── schemas.py   # Request/response models
├── agents/          # Pydantic-AI agents (optimizer, reviewer, etc.)
├── filters/         # Validation plugins (ATS, keywords, hallucination)
├── services/        # Rendering, scraping, caching, Supabase
│   └── scrapers/    # Job scraper implementations
├── models/          # Pydantic data models
├── orchestration.py # Core optimization loop
└── cli.py           # Click CLI

frontend/src/
├── app/             # Next.js App Router pages
├── components/      # React components
├── hooks/           # Custom React hooks
├── lib/             # Utilities (Supabase, API client)
└── types/           # TypeScript types
```

**Agents**: job_parser, optimizer, combined_reviewer, name_extractor, hallucination_detector, ai_generated_detector

**Filters** (run by priority):
0. ContentLengthChecker - Pre-render size check
1. DataValidator - HTML structure validation
3. HallucinationChecker - Detect fabrications
4. KeywordMatcher - TF-IDF matching
5. LLMChecker - ATS simulation
6. VectorSimilarityMatcher - Semantic similarity
7. AIGeneratedChecker - Detect AI-sounding text

## Development

```bash
# Run tests
uv run pytest tests/

# Install dev dependencies
uv sync --group dev

# Run API in dev mode
uv run uvicorn hr_breaker.api.main:app --reload

# Run frontend in dev mode
cd frontend && npm run dev
```

## License

MIT
