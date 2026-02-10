# Combine LLM Filters for Faster Pipeline

**Date:** 2026-02-10
**Status:** Approved
**Goal:** Reduce filter execution time by combining LLM calls

## Problem

The filter stage makes 3 separate LLM calls per iteration:
- HallucinationChecker (gemini-pro): 3-8s
- LLMChecker (gemini-flash + vision): 5-10s
- AIGeneratedChecker (gemini-flash): 3-8s

Total: 11-26s per iteration, mostly waiting on LLM round-trips.

## Solution

Merge HallucinationChecker and AIGeneratedChecker into a single `ContentIntegrityChecker` that performs both checks in one LLM call.

### New Agent: `content_integrity.py`

```python
class ContentIntegrityResult(BaseModel):
    # Hallucination fields
    no_hallucination_score: float  # 0.0-1.0
    hallucination_concerns: list[str]

    # AI detection fields
    ai_probability: float  # 0.0-1.0
    ai_indicators: list[str]
```

**Model:** gemini-flash (faster than pro, sufficient for this task)

**Prompt structure:**
1. Task 1: Hallucination check (compare original vs optimized)
2. Task 2: AI-generation check (analyze optimized text)
3. Return combined structured response

### New Filter: `content_integrity_checker.py`

- Priority: 3 (same as current HallucinationChecker)
- Replaces: HallucinationChecker + AIGeneratedChecker
- Pass condition: `hallucination_score >= 0.9 AND ai_probability < 0.5`

### Files to Change

| File | Action |
|------|--------|
| `agents/content_integrity.py` | Create |
| `filters/content_integrity_checker.py` | Create |
| `agents/hallucination_detector.py` | Delete |
| `agents/ai_generated_detector.py` | Delete |
| `filters/hallucination_checker.py` | Delete |
| `filters/ai_generated_checker.py` | Delete |
| `filters/__init__.py` | Update imports |
| `agents/__init__.py` | Update imports |
| `orchestration.py` | Remove old filter imports |

## Expected Impact

**Before:** 3 LLM calls, 11-26s
**After:** 2 LLM calls, 9-20s
**Savings:** ~3-8s per iteration (one fewer LLM round-trip)

## Implementation Steps

1. Create `agents/content_integrity.py` with combined prompt
2. Create `filters/content_integrity_checker.py`
3. Update `filters/__init__.py` to export new filter
4. Update `agents/__init__.py` to export new agent
5. Delete old hallucination and AI-generated files
6. Update `orchestration.py` imports
7. Run tests to verify behavior
