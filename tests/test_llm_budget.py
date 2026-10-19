from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from caf_l3.llm import BudgetExhaustedError, GeminiClassifier


@pytest.mark.parametrize("cap", [0, -1, float("nan"), float("inf")])
def test_classifier_rejects_invalid_budget(monkeypatch, cap):
    monkeypatch.setattr(GeminiClassifier, "_load_models_config", lambda self: {"budget": {"max_usd_per_run": cap}})
    with pytest.raises(ValueError, match="finite and positive"):
        GeminiClassifier(Mock())


def test_classifier_stops_retries_after_estimated_budget(monkeypatch):
    monkeypatch.setattr(GeminiClassifier, "_load_models_config", lambda self: {
        "models": {"primary": "fixture", "fallbacks": ["fallback"]},
        "budget": {"max_usd_per_run": 0.1},
        "pricing": {"fixture": {"input": 1, "output": 1}},
    })
    classifier = GeminiClassifier(Mock())
    response = SimpleNamespace(text="invalid JSON", usage_metadata=SimpleNamespace(
        prompt_token_count=200_000, candidates_token_count=0))
    classifier.client = Mock()
    classifier.client.models.generate_content.return_value = response
    monkeypatch.setattr(classifier, "is_available", lambda: True)
    monkeypatch.setattr(classifier, "build_candidate_prompt", lambda paper: ("candidates", {}))
    monkeypatch.setattr("caf_l3.llm.time.sleep", lambda seconds: None)
    with pytest.raises(BudgetExhaustedError):
        classifier.classify_unit("s2023.P1", "Question")
    assert classifier.total_cost_usd == 0.2
    assert classifier.client.models.generate_content.call_count == 1


def test_classifier_rejects_call_at_budget(monkeypatch):
    classifier = GeminiClassifier(Mock())
    classifier.total_cost_usd = classifier.budget_cap
    classifier.client = Mock()
    monkeypatch.setattr(classifier, "is_available", lambda: True)
    monkeypatch.setattr(classifier, "build_candidate_prompt", lambda paper: ("candidates", {}))
    with pytest.raises(BudgetExhaustedError):
        classifier.classify_unit("s2023.P1", "Question")
    classifier.client.models.generate_content.assert_not_called()
