# Next.js Frontend with Supabase Backend

## Overview

Replace the Streamlit UI with a modern Next.js frontend featuring multi-CV management, user accounts, and customizable themes. Keep the existing Python agents and filters, wrap them with a FastAPI backend.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                         │
│  (React, Tailwind CSS, theme system, Supabase client SDK)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Supabase                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Auth        │  │ Postgres    │  │ Storage                 │  │
│  │ (Google)    │  │ (users, cvs,│  │ (CV files, generated    │  │
│  │             │  │  jobs, runs)│  │  PDFs)                  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                           │
│  (Existing agents, filters, orchestration, WeasyPrint)          │
│  - Authenticated via Supabase JWT                               │
│  - Reads/writes to Supabase DB & Storage                        │
└─────────────────────────────────────────────────────────────────┘
```

**Flow**: User authenticates via Supabase → Next.js gets JWT → Frontend calls FastAPI with JWT in header → FastAPI validates JWT and scopes all queries to that user.

## Database Schema

```sql
-- Users table (managed by Supabase Auth, extended with profile)
profiles (
  id           UUID PRIMARY KEY REFERENCES auth.users(id),
  email        TEXT,
  name         TEXT,
  theme        TEXT DEFAULT 'minimal',  -- 'minimal' | 'professional' | 'bold'
  created_at   TIMESTAMP DEFAULT NOW()
)

-- Uploaded CVs
cvs (
  id           UUID PRIMARY KEY,
  user_id      UUID REFERENCES profiles(id),
  name         TEXT,                     -- Display name (e.g., "Software Engineer CV")
  file_path    TEXT,                     -- Path in Supabase Storage
  original_filename TEXT,
  content_text TEXT,                     -- Extracted text for LLM
  created_at   TIMESTAMP DEFAULT NOW()
)

-- Optimization runs
optimization_runs (
  id           UUID PRIMARY KEY,
  user_id      UUID REFERENCES profiles(id),
  cv_id        UUID REFERENCES cvs(id),
  job_input    TEXT,                     -- URL or pasted text
  job_parsed   JSONB,                    -- Parsed job data (title, company, requirements)
  status       TEXT,                     -- 'pending' | 'running' | 'completed' | 'failed'
  current_step TEXT,                     -- For progress display
  iterations   INTEGER DEFAULT 0,
  result_html  TEXT,                     -- Final optimized HTML
  result_pdf_path TEXT,                  -- Path in Supabase Storage
  feedback     JSONB,                    -- Filter results/feedback
  created_at   TIMESTAMP DEFAULT NOW()
)
```

Row-level security policies ensure users only see their own data. Supabase Storage has a folder per user (`{user_id}/cvs/` and `{user_id}/results/`).

## API Endpoints

```
POST   /auth/verify          - Verify Supabase JWT, return user info

# CVs
GET    /cvs                  - List user's CVs
POST   /cvs                  - Upload new CV (multipart form)
GET    /cvs/{id}             - Get CV details
DELETE /cvs/{id}             - Delete CV

# Optimization
POST   /optimize             - Start optimization run
                               Body: { cv_id, job_input }
                               Returns: { run_id }

GET    /optimize/{run_id}    - Get run status & progress
                               Returns: { status, current_step, steps[], result? }

GET    /optimize/{run_id}/pdf - Download generated PDF

# User
GET    /me                   - Get current user profile
PATCH  /me                   - Update profile (theme, name)
```

Progress updates via polling (GET /optimize/{run_id} every 2 seconds).

## Frontend Structure

```
app/
├── (auth)/
│   └── login/page.tsx        - Google sign-in button
├── (protected)/
│   ├── layout.tsx            - Auth guard, navbar, theme provider
│   ├── dashboard/page.tsx    - CV list, upload, manage
│   ├── optimize/page.tsx     - Select CV, enter job, start run
│   ├── results/[id]/page.tsx - View result, download PDF, filter feedback
│   └── settings/page.tsx     - Theme switcher, account info
└── api/                      - (Optional) proxy routes if needed

components/
├── ui/                       - Base components (Button, Input, Card, etc.)
├── CVCard.tsx               - CV preview card with actions
├── CVDropdown.tsx           - CV selector for optimize page
├── JobInput.tsx             - Auto-detect URL/text input
├── ProgressStepper.tsx      - Step-by-step progress visualization
├── ThemeSwitcher.tsx        - 3-option theme toggle
└── ResumePreview.tsx        - HTML resume preview with PDF download
```

**Libraries:**
- Tailwind CSS - Styling with theme CSS variables
- shadcn/ui - Pre-built accessible components
- @supabase/supabase-js - Auth & database client
- react-query - Data fetching, caching, polling

## Theme System

Three themes via CSS variables:

```css
/* Minimal - clean, lots of whitespace */
:root[data-theme="minimal"] {
  --color-bg: #ffffff;
  --color-text: #1a1a1a;
  --color-primary: #000000;
  --color-accent: #666666;
  --border-radius: 4px;
  --font-heading: 'Inter', sans-serif;
}

/* Professional - trust-inspiring, subtle depth */
:root[data-theme="professional"] {
  --color-bg: #f8fafc;
  --color-text: #0f172a;
  --color-primary: #1e40af;
  --color-accent: #3b82f6;
  --border-radius: 8px;
  --font-heading: 'Source Sans Pro', sans-serif;
}

/* Bold - strong colors, distinctive */
:root[data-theme="bold"] {
  --color-bg: #0a0a0a;
  --color-text: #fafafa;
  --color-primary: #22d3ee;
  --color-accent: #f472b6;
  --border-radius: 12px;
  --font-heading: 'Space Grotesk', sans-serif;
}
```

Theme stored in `profiles.theme`, applied via `data-theme` attribute on `<html>`.

## Progress Stepper

5 stages displayed as horizontal stepper:

```
[✓ Parse Job] → [✓ Generate] → [● Validate] → [○ Refine] → [○ Complete]
```

| Stage | Description | Backend trigger |
|-------|-------------|-----------------|
| Parse Job | Extract requirements from URL/text | job_parser agent completes |
| Generate | Create optimized HTML resume | optimizer agent completes |
| Validate | Run filters (ATS, keywords, etc.) | Filter pipeline starts |
| Refine | Re-generate if filters fail (loop) | On filter rejection |
| Complete | All checks passed, PDF ready | Final PDF rendered |

Visual states: Done (✓ green), Current (● pulsing), Pending (○ gray).

## Backend Changes

**Unchanged:**
- All agents (job_parser, optimizer, combined_reviewer, etc.)
- All filters and registry system
- orchestration.py core loop
- renderer.py (WeasyPrint)
- Job scrapers

**New/Modified:**

```
src/hr_breaker/api/
├── __init__.py
├── main.py          - FastAPI app, CORS, middleware
├── auth.py          - JWT verification via Supabase
├── routes/
│   ├── cvs.py       - CV CRUD endpoints
│   ├── optimize.py  - Optimization endpoints
│   └── users.py     - Profile endpoints
└── deps.py          - Dependencies (get_current_user, db session)
```

- New `services/supabase.py` for DB and storage operations
- Modified orchestration to update optimization_runs table with progress
- Remove Streamlit code

## Project Structure

```
hr-breaker/
├── frontend/          - Next.js app (new)
├── src/hr_breaker/
│   ├── api/           - FastAPI app (new)
│   ├── agents/        - (unchanged)
│   ├── filters/       - (unchanged)
│   ├── services/      - + supabase.py
│   └── ...
└── supabase/          - migrations, RLS policies (new)
```

## Out of Scope (MVP)

- Batch job applications
- Resume version history
- Sharing/collaboration
- Email notifications
- Mobile-specific layouts
