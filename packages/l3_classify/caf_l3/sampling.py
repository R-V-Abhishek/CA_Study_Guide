"""Reproducible root samples with duplicate groups and frozen development splits."""

import random
import re

from caf_l2.revisions import digest


def duplicate_key(context: dict) -> str:
    def text(parts):
        return [value for part in parts for value in [part['question_text'], *text(part['parts'])]]
    value = '\n'.join([context['common_stem'], context['question_text'], *text(context['parts'])])
    return digest({'paper_id': context['paper_id'], 'text': re.sub(r'\s+', ' ', value).strip().casefold()})


def stratified_sample(records: list[dict], *, per_paper: int = 20, seed: int = 42) -> dict:
    rng = random.Random(seed)
    selected = []
    missing = []
    groups = {}
    for record in records:
        groups.setdefault(duplicate_key(record['context']), []).append(record)
    for paper in [f's2023.P{i}' for i in range(1, 7)]:
        strata = {}
        for key, occurrences in sorted(groups.items()):
            record = min(occurrences, key=lambda r: (r['document_id'], r['question_id']))
            context = record['context']
            if context['paper_id'] != paper:
                continue
            difficulty = 'case' if len(context['classification_part_ids']) > 2 else context['answer_status']
            stratum = (context['source_family'], context.get('source_attempt_id'), difficulty)
            strata.setdefault(stratum, []).append((key, record, occurrences))
        available = sorted(strata, key=lambda s: tuple(str(x) for x in s))
        for values in strata.values():
            rng.shuffle(values)
        chosen = []
        while available and len(chosen) < per_paper:
            for stratum in list(available):
                if len(chosen) >= per_paper:
                    break
                key, record, occurrences = strata[stratum].pop()
                chosen.append(dict(question_id=record['question_id'], document_id=record['document_id'],
                    extraction_revision_id=record['extraction_revision_id'], paper_id=paper,
                    duplicate_group=key, duplicate_occurrences=[r['question_id'] for r in occurrences],
                    stratum=list(stratum)))
                if not strata[stratum]:
                    available.remove(stratum)
        if len(chosen) < per_paper:
            missing.append(dict(paper_id=paper, requested=per_paper, available=len(chosen)))
        # Each duplicate group contributes one root and never crosses partitions.
        for index, item in enumerate(chosen):
            item['partition'] = 'development' if index % 2 == 0 else 'holdout'
            item['blind_comparison'] = index < 5
            item['pilot'] = index < 2
        selected.extend(chosen)
    return dict(seed=seed, requested_per_paper=per_paper, roots=selected,
        unavailable_strata=missing, observed_strata=sorted({str(r['stratum']) for r in selected}),
        duplicate_grouping='normalized complete question text within paper; one occurrence sampled')
