"""Index drafts carry immutable source evidence and never imply approval."""

from caf_l0.index_candidates import draft_candidates
from caf_l0.index_parser import parse_index_pages
from dataclasses import asdict


def test_roman_units_and_draft_candidate_source_evidence():
    entries, unresolved = parse_index_pages([(5, 'DETAILED CONTENTS MODULE 4\nCHAPTER 1: Customs\nUNIT I- Introduction\n1. Basic concepts ... 1.2\nUNIT II- Levy\n1. Assessment ... 1.29')])
    assert not unresolved
    assert [entry.number for entry in entries if entry.kind == 'unit'] == ['I', 'II']
    index = dict(sha256='a' * 64, entries=[asdict(entry) for entry in entries])
    args = dict(paper_id='s2023.P5', download_url='https://resource.cdn.icai.org/example.pdf',
        edition='September 2025', applicable_attempts=['2026-05', '2026-09', '2027-01'])
    candidates = draft_candidates(index, **args)
    assert len(candidates) == 2
    assert candidates == draft_candidates(index, **args)
    assert all(c['descriptor']['approved'] is False for c in candidates)
    assert all(c['textbook_references'][0]['sha256'] == index['sha256'] for c in candidates)
    assert candidates[-1]['path'][-2]['name'] == 'Levy'
    assert candidates[-1]['descriptor']['applicable_attempts'] == args['applicable_attempts']
    assert '2027-05' not in candidates[-1]['descriptor']['applicable_attempts']
