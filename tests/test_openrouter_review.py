"""Frozen complete-question reviews, free-only requests and resumable outputs."""

import json

import httpx
import pytest

from caf_l2.revisions import digest
from caf_l3.openrouter import (CatalogModel, classify_record, free_models, load_results,
    result_path, review_manifest, run_review)


def model():
    return dict(id="test/classifier:free", name="Test", created=1, context_length=100000,
        supported_parameters=["response_format", "structured_outputs"],
        pricing=dict(prompt="0", completion="0"))


def batch():
    record = dict(question_id="root/unsafe", document_id=1, extraction_revision_id=2,
        context=dict(paper_id="s2023.P1", common_stem="Shared scenario", question_text="Calculate impairment",
            parts=[], classification_part_ids=["part-a"]),
        candidates=[dict(node_id="n1", paper_id="s2023.P1")])
    record["input_hash"] = digest(record)
    manifest = dict(schema_version=1, records=[record], classifier=dict(method="codex", model_id="old"))
    manifest["batch_key"] = digest(manifest)
    return review_manifest(manifest, model()["id"])


def output(record):
    return dict(question_id=record["question_id"], input_hash=record["input_hash"], mappings=[
        dict(part_id="part-a", outcome="matched", primary_node_id="n1", secondary_node_ids=[],
            evidence=[dict(node_id="n1", support="Impairment is explicitly calculated")],
            note="Tests impairment rather than incidental lease facts", confidence=.9, bucket="A")])


def completion(record):
    return dict(id="response-1", model="test/classifier", provider="test-provider",
        choices=[dict(message=dict(content=json.dumps(output(record))), finish_reason="stop")],
        usage=dict(prompt_tokens=100, completion_tokens=80, cost=0))


def test_catalog_filters_paid_expired_and_missing_features():
    paid = {**model(), "id": "paid:free", "pricing": dict(prompt="0.01", completion="0")}
    expired = {**model(), "id": "expired:free", "expiration_date": "2020-01-01"}
    unsupported = {**model(), "id": "unsupported:free", "supported_parameters": []}
    missing_price = {**model(), "id": "missing:free", "pricing": {}}
    request_fee = {**model(), "id": "request:free", "pricing": dict(prompt="0", completion="0", request="0.1")}
    router = {**model(), "id": "openrouter/auto", "top_provider": dict(
        context_length=None, max_completion_tokens=None)}
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        json=dict(data=[model(), paid, expired, unsupported, missing_price, request_fee, router])))) as client:
        assert [m.id for m in free_models(client)] == [model()["id"]]


def test_catalog_cli_reports_network_failure_without_traceback(monkeypatch):
    from typer.testing import CliRunner
    from caf_cli import classification_review

    def unavailable(client):
        raise httpx.ConnectError("Private transport diagnostics")

    monkeypatch.setattr(classification_review, "free_models", unavailable)
    result = CliRunner().invoke(classification_review.app, ["models"])
    assert result.exit_code == 1
    assert "catalog unavailable (ConnectError)" in result.output
    assert "No model calls made" in result.output
    assert "Private transport diagnostics" not in result.output


def test_request_enforces_zero_cost_and_retains_full_context():
    record = batch()["records"][0]
    def respond(request):
        payload = json.loads(request.content)
        assert payload["provider"]["max_price"] == dict(prompt=0, completion=0, request=0)
        assert payload["provider"]["require_parameters"] is True
        assert payload["max_tokens"] == 8192
        assert json.loads(payload["messages"][1]["content"]) == record
        assert request.headers["authorization"] == "Bearer test-only-key"
        return httpx.Response(200, json=completion(record))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        saved = classify_record(client, record, CatalogModel(**model()), "test-only-key")
    assert saved["execution"]["model_id"] == "test/classifier"
    assert saved["execution"]["requested_model_id"] == model()["id"]
    assert "test-only-key" not in json.dumps(saved)


def test_large_composite_retains_every_part_with_larger_response_budget():
    record = batch()["records"][0]
    ids = [f"part-{index}" for index in range(104)]
    record["context"]["classification_part_ids"] = ids
    record["input_hash"] = digest({k: v for k, v in record.items() if k != "input_hash"})
    value = completion(record)
    result = output(record)
    result["mappings"] = [{**result["mappings"][0], "part_id": part_id} for part_id in ids]
    value["choices"][0]["message"]["content"] = json.dumps(result)

    def respond(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 57344
        assert request.extensions["timeout"]["read"] > 90
        assert request.extensions["timeout"]["connect"] == 10
        assert json.loads(payload["messages"][1]["content"])["context"]["classification_part_ids"] == ids
        return httpx.Response(200, json=value)

    available = {**model(), "top_provider": dict(context_length=100000, max_completion_tokens=131072)}
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        saved = classify_record(client, record, CatalogModel(**available), "test")
    assert len(saved["result"]["mappings"]) == 104
    assert saved["execution"]["max_output_tokens"] == 57344


@pytest.mark.parametrize("limits, message", [
    (dict(context_length=100000, max_completion_tokens=8192), "completion limit"),
    (dict(context_length=1000, max_completion_tokens=131072), "context bound"),
])
def test_large_composite_exceeding_published_limits_makes_no_call(limits, message):
    record = batch()["records"][0]
    record["context"]["classification_part_ids"] = [f"part-{index}" for index in range(104)]
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request))) as client:
        with pytest.raises(ValueError, match=message):
            classify_record(client, record, CatalogModel(**{**model(), "top_provider": limits}), "test")
    assert calls == []


@pytest.mark.parametrize("mutation", ["unknown", "missing_part", "truncated", "charge", "no_evidence"])
def test_rejects_incomplete_or_unsupported_provider_results(mutation):
    record = batch()["records"][0]
    value = completion(record)
    result = output(record)
    if mutation == "unknown":
        result["mappings"][0]["primary_node_id"] = "invented"
    elif mutation == "missing_part":
        result["mappings"] = []
    elif mutation == "truncated":
        value["choices"][0]["finish_reason"] = "length"
    elif mutation == "charge":
        value["usage"]["cost"] = .01
    else:
        result["mappings"][0]["evidence"] = []
    value["choices"][0]["message"]["content"] = json.dumps(result)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=value))) as client:
        with pytest.raises(RuntimeError):
            classify_record(client, record, CatalogModel(**model()), "test", retries=0)


def test_resumes_without_more_model_calls_and_hashes_filenames(tmp_path):
    manifest = batch()
    calls = []
    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=dict(data=[model()]) if request.method == "GET"
            else completion(manifest["records"][0]))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert run_review(manifest, tmp_path, "test", client=client)["completed"] == 1
        assert run_review(manifest, tmp_path, "test", client=client)["pending"] == 0
    assert calls == ["GET", "POST"]
    assert result_path(tmp_path, "root/unsafe").parent == tmp_path
    assert len(load_results(manifest, tmp_path)) == 1
    saved = json.loads(result_path(tmp_path, "root/unsafe").read_text())
    saved["batch_key"] = "other"
    result_path(tmp_path, "root/unsafe").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="another"):
        load_results(manifest, tmp_path)


def test_paid_model_disappears_and_no_completion_is_sent(tmp_path):
    calls = []
    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=dict(data=[]))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match="not currently free"):
            run_review(batch(), tmp_path, "test", client=client)
    assert calls == ["GET"]


def test_rate_limit_retries_bounded_and_does_not_leak_provider_error(tmp_path, monkeypatch):
    monkeypatch.setattr("caf_l3.openrouter.time.sleep", lambda delay: None)
    calls = []
    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=dict(data=[model()])) if request.method == "GET" else httpx.Response(
            429, json=dict(error="secret should never be saved"))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        state = run_review(batch(), tmp_path, "test", client=client)
    assert calls == ["GET", "POST", "POST", "POST"]
    assert state["completed"] == 0 and state["pending"] == 1
    assert "HTTP 429" in next(iter(state["failures"].values()))
    assert "secret" not in json.dumps(state)


def test_catalog_network_failure_prevents_model_calls(tmp_path):
    def respond(request):
        raise httpx.ConnectError("DNS unavailable")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(RuntimeError, match="catalog"):
            run_review(batch(), tmp_path, "test", client=client)


def test_paid_model_not_accepted_for_frozen_review():
    with pytest.raises(ValueError, match=":free"):
        review_manifest(batch(), "paid/model")
