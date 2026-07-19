from hr_breaker.config import get_settings


def test_hallucination_gate_uses_config_threshold(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("FILTER_HALLUCINATION_THRESHOLD", "0.8")
    s = get_settings()
    assert s.filter_hallucination_threshold == 0.8
    # A hallucination score of 0.85 must PASS under an 0.8 gate.
    from hr_breaker.agents.content_integrity import _hallucination_passed

    assert _hallucination_passed(0.85) is True
    assert _hallucination_passed(0.75) is False
    get_settings.cache_clear()


def test_ai_gate_uses_config_threshold(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("FILTER_AI_GENERATED_THRESHOLD", "0.4")
    from hr_breaker.agents.content_integrity import _ai_passed

    # ai_probability below threshold passes.
    assert _ai_passed(0.3) is True
    assert _ai_passed(0.5) is False
    get_settings.cache_clear()
