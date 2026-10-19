"""Corrected paper packs retain the complete corpus exactly once."""

import json

import pytest

from caf_l3.corpus_review import PAPER_PACKS, corpus_status, render_corpus


@pytest.fixture
def corpus(tmp_path):
    for number in range(1, 7):
        directory = tmp_path / f"P{number}"
        directory.mkdir()
        (directory / "index.json").write_text(json.dumps([
            dict(question_id=f"q{number}", gradable_parts=2)]))
    for paper, packs in PAPER_PACKS.items():
        for index, name in enumerate(packs):
            directory = tmp_path / name
            directory.mkdir(exist_ok=True)
            items = [dict(question_id=f"q{paper[1:]}", gradable_parts=2)] if index == 0 else []
            (directory / "index.json").write_text(json.dumps(items))
    return tmp_path


def test_status_counts_only_saved_root_outputs(corpus):
    directory = corpus / "P1-corrected" / "results-direct"
    directory.mkdir()
    (directory / "q1.json").write_text(json.dumps(dict(result=dict(question_id="q1", mappings=[{}, {}]))))
    status = corpus_status(corpus)
    assert (status["total"], status["saved"], status["pending"]) == (6, 1, 5)
    assert status["papers"]["P1"]["saved_parts"] == 2


def test_duplicate_and_missing_roots_are_rejected(corpus):
    path = corpus / "P2-rerouted" / "index.json"
    path.write_text(json.dumps([dict(question_id="q1", gradable_parts=2)]))
    with pytest.raises(ValueError, match="more than one"):
        corpus_status(corpus)
    path.write_text("[]")
    (corpus / "P1-corrected" / "index.json").write_text("[]")
    with pytest.raises(ValueError, match="cover the original corpus"):
        corpus_status(corpus)


def test_incomplete_report_requires_explicit_interim_choice(corpus):
    output = corpus / "review.md"
    with pytest.raises(ValueError, match="still lack classifications"):
        render_corpus(corpus, output)
    assert not output.exists()


def test_existing_student_edits_are_preserved(corpus):
    output = corpus / "review.md"
    output.write_text("Student corrections")
    with pytest.raises(ValueError, match="preserve student edits"):
        render_corpus(corpus, output, allow_pending=True)
    assert output.read_text() == "Student corrections"


def test_interim_render_uses_one_snapshot_while_workers_continue(corpus, monkeypatch):
    calls = []

    def load(directory, *, result_ids):
        calls.append((directory.name, result_ids))
        # A new checkpoint arriving during rendering belongs to the next report.
        results = directory / "results-direct"
        results.mkdir(exist_ok=True)
        if directory.name == "P1-corrected":
            (results / "q1.json").write_text(json.dumps(dict(result=dict(question_id="q1", mappings=[{}, {}]))))
        return {"records": []}, {}

    monkeypatch.setattr("caf_l3.corpus_review.load_review", load)
    monkeypatch.setattr("caf_l3.corpus_review.render_review_markdown", lambda manifest, results: "Questions\n")
    output = corpus / "review.md"
    status = render_corpus(corpus, output, allow_pending=True)
    assert status["saved"] == 0
    assert all(not result_ids for _, result_ids in calls)
    assert "INTERIM" in output.read_text()
    assert "Saved AI outputs: 0" in output.read_text()
    assert corpus_status(corpus)["saved"] == 1


def test_wrong_paper_cannot_be_rendered_even_as_interim(corpus, monkeypatch):
    monkeypatch.setattr("caf_l3.corpus_review.load_review", lambda directory, **kwargs:
        ({"records": [{"context": {"paper_id": "s2023.P6"}}]}, {}))
    output = corpus / "review.md"
    with pytest.raises(ValueError, match="wrong final paper"):
        render_corpus(corpus, output, allow_pending=True)
    assert not output.exists()
