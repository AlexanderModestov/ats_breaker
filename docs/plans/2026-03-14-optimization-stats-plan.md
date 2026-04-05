# Optimization Stats Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a stats page showing total optimization count and most frequently requested skills/keywords from job postings.

**Architecture:** New backend endpoint aggregates `job_parsed` data from existing `optimization_runs` table. New frontend page displays the results as a simple ranked list.

**Tech Stack:** FastAPI, Pydantic, Supabase, Next.js, React Query, Tailwind CSS

---

### Task 1: Backend — Pydantic Schemas

**Files:**
- Modify: `src/hr_breaker/api/schemas.py:134-140` (before HealthResponse)

**Step 1: Add schemas to `api/schemas.py`**

Add before the `HealthResponse` class:

```python
# Stats schemas
class KeywordStat(BaseModel):
    """A keyword with its frequency count."""

    keyword: str
    count: int


class OptimizationStatsResponse(BaseModel):
    """Aggregated optimization statistics."""

    total_optimizations: int
    completed_optimizations: int
    top_keywords: list[KeywordStat]
```

**Step 2: Commit**

```bash
git add src/hr_breaker/api/schemas.py
git commit -m "feat: add stats response schemas"
```

---

### Task 2: Backend — Supabase Aggregation Method

**Files:**
- Modify: `src/hr_breaker/services/supabase.py:310-317` (after `delete_optimization_run`)
- Test: `tests/test_stats.py` (create)

**Step 1: Write the failing test**

Create `tests/test_stats.py`:

```python
"""Tests for optimization stats aggregation."""

from collections import Counter

from hr_breaker.services.supabase import SupabaseService


def _make_runs(runs_data: list[dict]) -> list[dict]:
    """Helper to create mock optimization run records."""
    return [
        {
            "status": r.get("status", "complete"),
            "job_parsed": r.get("job_parsed"),
        }
        for r in runs_data
    ]


class TestAggregateKeywords:
    """Test the keyword aggregation logic."""

    def test_empty_runs(self):
        result = SupabaseService.aggregate_keywords([])
        assert result == {}

    def test_single_run_with_keywords(self):
        runs = _make_runs([
            {
                "status": "complete",
                "job_parsed": {
                    "keywords": ["Python", "React"],
                    "requirements": [],
                },
            }
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result == {"python": 1, "react": 1}

    def test_multiple_runs_aggregate(self):
        runs = _make_runs([
            {
                "status": "complete",
                "job_parsed": {
                    "keywords": ["Python", "AWS"],
                    "requirements": ["3+ years Python experience"],
                },
            },
            {
                "status": "complete",
                "job_parsed": {
                    "keywords": ["Python", "React"],
                    "requirements": ["React experience required"],
                },
            },
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result["python"] == 3  # 2 from keywords + 1 from requirements
        assert result["react"] == 2  # 1 from keywords + 1 from requirements
        assert result["aws"] == 1

    def test_skips_non_complete_runs(self):
        runs = _make_runs([
            {
                "status": "failed",
                "job_parsed": {
                    "keywords": ["Python"],
                    "requirements": [],
                },
            },
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result == {}

    def test_skips_runs_without_job_parsed(self):
        runs = _make_runs([
            {"status": "complete", "job_parsed": None},
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result == {}

    def test_normalizes_case(self):
        runs = _make_runs([
            {
                "status": "complete",
                "job_parsed": {
                    "keywords": ["Python", "PYTHON", "python"],
                    "requirements": [],
                },
            },
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result == {"python": 3}

    def test_extracts_keywords_from_requirement_sentences(self):
        """Requirements are full sentences - extract individual words and match known keywords."""
        runs = _make_runs([
            {
                "status": "complete",
                "job_parsed": {
                    "keywords": ["Python", "Docker"],
                    "requirements": ["Experience with Python and Docker in production"],
                },
            },
        ])
        result = SupabaseService.aggregate_keywords(runs)
        assert result["python"] == 2  # once from keywords, once from requirements
        assert result["docker"] == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stats.py -v`
Expected: FAIL with AttributeError — `aggregate_keywords` doesn't exist yet.

**Step 3: Implement `aggregate_keywords` static method**

Add to `SupabaseService` class in `services/supabase.py` after `delete_optimization_run`:

```python
    @staticmethod
    def aggregate_keywords(runs: list[dict[str, Any]]) -> dict[str, int]:
        """
        Aggregate keyword frequencies from completed optimization runs.

        Extracts keywords from job_parsed['keywords'] and scans
        job_parsed['requirements'] for mentions of those keywords.

        Returns:
            Dict mapping lowercase keyword to frequency count.
        """
        from collections import Counter

        keyword_counts: Counter[str] = Counter()
        # First pass: collect all known keywords across all runs
        all_known_keywords: set[str] = set()
        complete_runs = []
        for run in runs:
            if run.get("status") != "complete":
                continue
            job_parsed = run.get("job_parsed")
            if not job_parsed:
                continue
            complete_runs.append(job_parsed)
            for kw in job_parsed.get("keywords", []):
                all_known_keywords.add(kw.strip().lower())

        # Second pass: count keywords and scan requirements
        for job_parsed in complete_runs:
            for kw in job_parsed.get("keywords", []):
                keyword_counts[kw.strip().lower()] += 1

            for req in job_parsed.get("requirements", []):
                req_lower = req.lower()
                for kw in all_known_keywords:
                    if kw in req_lower:
                        keyword_counts[kw] += 1

        return dict(keyword_counts)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stats.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hr_breaker/services/supabase.py tests/test_stats.py
git commit -m "feat: add keyword aggregation logic with tests"
```

---

### Task 3: Backend — Stats API Endpoint

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py:355-380` (after `delete_optimization`)
- Modify: `src/hr_breaker/services/supabase.py` (add `get_stats_data` method)

**Step 1: Add `get_stats_data` method to `SupabaseService`**

Add after `aggregate_keywords`:

```python
    def get_stats_data(self, user_id: str) -> list[dict[str, Any]]:
        """Get minimal optimization run data for stats aggregation."""
        try:
            result = (
                self._client.table("optimization_runs")
                .select("status, job_parsed")
                .eq("user_id", user_id)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to get stats data: {e}")
            raise SupabaseError(f"Failed to get stats data: {e}") from e
```

**Step 2: Add stats endpoint to `api/routes/optimize.py`**

Add import at top of file:

```python
from hr_breaker.api.schemas import (
    ...,
    KeywordStat,
    OptimizationStatsResponse,
)
```

Add after the `delete_optimization` route:

```python
@router.get("/stats", response_model=OptimizationStatsResponse)
async def get_optimization_stats(
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationStatsResponse:
    """Get aggregated optimization statistics for the current user."""
    runs = supabase.get_stats_data(user_id)
    total = len(runs)
    completed = sum(1 for r in runs if r.get("status") == "complete")
    keyword_counts = SupabaseService.aggregate_keywords(runs)

    top_keywords = [
        KeywordStat(keyword=kw, count=count)
        for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    ]

    return OptimizationStatsResponse(
        total_optimizations=total,
        completed_optimizations=completed,
        top_keywords=top_keywords,
    )
```

**IMPORTANT:** The `/stats` route must be registered BEFORE `/{run_id}` routes in the router, otherwise FastAPI will match "stats" as a `run_id` path parameter. Move it above the `GET /{run_id}` route.

**Step 3: Commit**

```bash
git add src/hr_breaker/services/supabase.py src/hr_breaker/api/routes/optimize.py src/hr_breaker/api/schemas.py
git commit -m "feat: add GET /api/optimizations/stats endpoint"
```

---

### Task 4: Frontend — Types and API Function

**Files:**
- Modify: `frontend/src/types/index.ts:94-96` (after OptimizationListResponse)
- Modify: `frontend/src/lib/api.ts:146-147` (after deleteOptimization)

**Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts` after `OptimizationListResponse`:

```typescript
export interface KeywordStat {
  keyword: string;
  count: number;
}

export interface OptimizationStatsResponse {
  total_optimizations: number;
  completed_optimizations: number;
  top_keywords: KeywordStat[];
}
```

**Step 2: Add API function**

Add to `frontend/src/lib/api.ts`:

Import `OptimizationStatsResponse` in the import block at the top.

Add after `deleteOptimization`:

```typescript
export async function getOptimizationStats(): Promise<OptimizationStatsResponse> {
  return fetchWithAuth<OptimizationStatsResponse>("/optimize/stats");
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add stats types and API function"
```

---

### Task 5: Frontend — useStats Hook

**Files:**
- Create: `frontend/src/hooks/useStats.ts`

**Step 1: Create the hook**

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { getOptimizationStats } from "@/lib/api";
import type { OptimizationStatsResponse } from "@/types";

export function useStats() {
  return useQuery<OptimizationStatsResponse, Error>({
    queryKey: ["optimization-stats"],
    queryFn: getOptimizationStats,
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useStats.ts
git commit -m "feat: add useStats hook"
```

---

### Task 6: Frontend — Stats Page

**Files:**
- Create: `frontend/src/app/(protected)/stats/page.tsx`

**Step 1: Create the stats page**

Follow the same patterns as `history/page.tsx` — use `motion`, `SlideUp`, `Card` components, loading shimmer, error state, empty state.

```tsx
"use client";

import { BarChart3 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { motion, SlideUp } from "@/components/motion";
import { useStats } from "@/hooks/useStats";

export default function StatsPage() {
  const { data: stats, isLoading, error } = useStats();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-8"
    >
      {/* Header */}
      <SlideUp className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Stats</h1>
        <p className="text-muted-foreground">
          Your optimization activity and top requested skills
        </p>
      </SlideUp>

      {/* Summary cards */}
      <SlideUp delay={0.1}>
        {isLoading && (
          <div className="grid gap-4 sm:grid-cols-2">
            {[1, 2].map((i) => (
              <div key={i} className="h-24 shimmer rounded-xl" />
            ))}
          </div>
        )}

        {error && (
          <Card className="border-destructive/50">
            <CardContent className="pt-6">
              <p className="text-destructive">
                Failed to load stats: {error.message}
              </p>
            </CardContent>
          </Card>
        )}

        {stats && (
          <div className="space-y-6">
            {/* Counts */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground">Total Optimizations</p>
                  <p className="text-3xl font-bold">{stats.total_optimizations}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground">Completed</p>
                  <p className="text-3xl font-bold">{stats.completed_optimizations}</p>
                </CardContent>
              </Card>
            </div>

            {/* Top keywords */}
            <Card>
              <CardContent className="pt-6">
                <h2 className="mb-4 text-lg font-semibold">Top Requested Skills</h2>
                {stats.top_keywords.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8">
                    <BarChart3 className="mb-4 h-12 w-12 text-muted-foreground/50" />
                    <p className="text-center text-muted-foreground">
                      No keyword data yet. Complete an optimization to see stats.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {stats.top_keywords.map((kw, i) => (
                      <div key={kw.keyword} className="flex items-center gap-3">
                        <span className="w-6 text-right text-sm text-muted-foreground">
                          {i + 1}.
                        </span>
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="font-medium capitalize">{kw.keyword}</span>
                            <span className="text-sm text-muted-foreground">
                              {kw.count} {kw.count === 1 ? "time" : "times"}
                            </span>
                          </div>
                          <div className="mt-1 h-2 overflow-hidden rounded-full bg-secondary">
                            <div
                              className="h-full rounded-full bg-primary transition-all"
                              style={{
                                width: `${(kw.count / stats.top_keywords[0].count) * 100}%`,
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </SlideUp>
    </motion.div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/\(protected\)/stats/page.tsx
git commit -m "feat: add stats page"
```

---

### Task 7: Frontend — Add Nav Link

**Files:**
- Modify: `frontend/src/components/Navbar.tsx:8-15`

**Step 1: Update Navbar**

Add `BarChart3` to the lucide-react import:

```typescript
import { LogOut, Settings, Sparkles, FileText, History, BarChart3 } from "lucide-react";
```

Add stats item to `navItems` array:

```typescript
const navItems = [
  { href: "/optimize", label: "Optimize", icon: Sparkles },
  { href: "/cvs", label: "CVs", icon: FileText },
  { href: "/history", label: "History", icon: History },
  { href: "/stats", label: "Stats", icon: BarChart3 },
];
```

**Step 2: Commit**

```bash
git add frontend/src/components/Navbar.tsx
git commit -m "feat: add Stats link to navbar"
```

---

### Task 8: Smoke Test

**Step 1: Run backend tests**

Run: `uv run pytest tests/test_stats.py -v`
Expected: All PASS

**Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS (no regressions)

**Step 3: Final commit if any fixes needed**
