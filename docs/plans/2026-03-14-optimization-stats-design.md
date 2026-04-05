# Optimization Stats Design

## Goal

Add a dedicated stats page showing users how many CVs they've optimized and which skills/keywords appear most frequently across their targeted job postings.

## Data Source

No new database tables. The existing `optimization_runs` table stores `job_parsed` (JSON) for each run, which contains `keywords` (list of strings) and `requirements` (list of strings) extracted from the job posting. Aggregation happens at query time.

## Backend

### New Supabase method

`SupabaseService.get_optimization_stats(user_id)` in `services/supabase.py`:

- Queries all optimization runs for the user, selecting `status` and `job_parsed` fields
- Filters to completed runs for keyword aggregation
- Extracts `keywords` and `requirements` from each run's `job_parsed`
- Normalizes keywords (lowercase, trimmed), counts with `Counter`
- Returns total count, completed count, and top N keywords (default 20)

### New API endpoint

`GET /api/optimizations/stats` in `api/routes/optimize.py`:

- Calls `get_optimization_stats()`
- Returns `OptimizationStatsResponse`

### New schemas in `api/schemas.py`

```python
class KeywordStat(BaseModel):
    keyword: str
    count: int

class OptimizationStatsResponse(BaseModel):
    total_optimizations: int
    completed_optimizations: int
    top_keywords: list[KeywordStat]
```

## Frontend

### New page

`frontend/src/app/(protected)/stats/page.tsx`:

- Heading with total optimization count
- Ranked list of top keywords with frequency counts
- Simple table/list layout, consistent with existing pages
- Loading and empty states

### New hook

`frontend/src/hooks/useStats.ts`:

- `useStats()` hook using `react-query` to fetch from the stats endpoint

### New API function

`frontend/src/lib/api.ts`:

- `getOptimizationStats()` function calling `GET /api/optimizations/stats`

### Nav update

Add "Stats" link to `Navbar.tsx`.

## What's NOT included

- No charts or visualizations
- No date range filters
- No new database tables or denormalized stats
- No resume-side skill tracking
