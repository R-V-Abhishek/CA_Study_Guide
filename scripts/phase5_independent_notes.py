"""Materialize manually authored blind comparison notes; this is not a classifier.

The decisions below were reasoned by the independent Codex agent from the
frozen question/candidate inputs before any Luna results existed. They are
provisional model comparisons, not student adjudications or training labels.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from caf_l2.revisions import digest
from caf_l3.batches import validated_mappings

# Explicit root-level observations, authored after inspecting the input context.
NOTES = {
    0: 'Hindi answer fragment computes FCFF equity value without the complete requested task; English lexical retrieval omits clear FCFF candidate evidence.',
    1: 'CSV incorrectly contains the case plus unrelated questions 1 through 6 and suggested answers; root boundary and attribution require extraction review.',
    2: 'Question 6 tests blockchain, joint/by-product inventory costing and acquisition valuation separately; some tested concepts are absent from the supplied candidate set.',
    3: 'MCQ answer choices have been extracted as twelve gradable parts; restore the actual NAV questions before attributing labels to choices.',
    4: 'Question 6 includes original questions and repeated answer portions; service-organisation audit, bank property and ethics/forensics attribution requires extraction correction.',
    5: 'Independent TDS cases and transfer-pricing tasks have sufficient shared context for provisional part labels.',
    6: 'GAAR and advance ruling tasks are explicit; the original audit-threshold task is not a listed gradable part.',
    7: 'GST supplies can be attributed provisionally; customs valuation has no suitable supplied label.',
    8: 'Penalty provision/reimbursement case lacks the requested MCQ or accounting task. Mention of joint operations does not establish the tested Ind AS 111 concept.',
    9: 'Root combines an elevator revenue case, segment-profit case and transition estimates statements; shared case boundaries are inconsistent.',
    10: 'Each MCQ asks option position and profit/loss from strike, spot price, premium and exercise/lapse: option payoff is the tested concept.',
    11: 'Infrastructure Debt Fund is an isolated heading without a question or shared context.',
    12: 'The complete task explicitly asks about an Audit Design Matrix for CAG performance audit; supplied candidates omit this concept.',
    13: 'Root mixes ethics acceptance, internal auditor assistance and cyber controls with repeated solution text; reconcile gradable question/answer boundaries first.',
    14: 'Revenue expenditure on scientific research is an isolated heading without the requested tax treatment or context.',
    15: 'Case Scenario III swallows business-trust MCQs and unrelated questions 1 and 3 through 6; root context/part identities are not reliable.',
    16: 'Local taxes paid is an isolated monetary input with no taxable valuation task or surrounding case.',
    17: 'GST registration threshold, supply and destroyed-import customs tasks need distinct labels; broad supply descriptors cannot substitute for missing specific registration/customs concepts.',
    18: 'IBS root contains solution bullet fragments for debt/equity strategy, ITC documents and intangible disclosures; the requested task is not preserved consistently for each part.',
    19: 'Embedded foreign-currency derivative journal entries and loan covenant breach classification are explicit separate accounting tasks.',
    20: 'Defined-benefit cost/remeasurement and conditional government-grant recognition are explicit; some table rows and repeated answer paragraphs are parsed as separate parts.',
    21: 'Root interleaves interest-rate case, startup theory and tokenisation questions with repeated solution bullets; attribution needs extraction review.',
    22: 'Interim review/going concern, consolidated audit and NOCLAR-versus-SA250 tasks are explicit, but repeated solution bullets must be identified as answer content.',
    23: 'Tax planning/evasion and advance-ruling admissibility tasks are explicit; one placeholder is not an independent gradable task.',
    24: 'Exam instructions about choosing questions are not a tested subject concept; no candidate fits.',
    25: 'Bank exemption/ITC and customs valuation specifics are absent from the supplied narrow GST candidates; online gaming supply valuation is also more specific than generic value definitions.',
    26: 'No penalty is leviable on CA firm is an isolated option without question context.',
    27: '137.95 lakhs is an isolated MCQ option without question context.',
    28: 'Root merges internal auditor thresholds, their solution, and the start of a different revenue-incentive case; restore complete root boundaries.',
    29: 'Root crosses machine valuation/charitable tax answer fragments into another IBS case; a single gradable paragraph mixes multiple unrelated tasks.',
}

# (part suffix, primary candidate index, secondary candidate indices, support)
LABELS = {
    2: [('Q6.a', 1, [], 'The question explicitly asks five impacts of blockchain on financial reporting.')],
    5: [('Q4.a.i', 1, [4], 'The task asks purchase-of-goods TDS and competing TCS consequences of a one-crore transaction, using purchaser/seller turnover.'),
        ('Q4.a.ii', 5, [3], 'Sales-agent commission tests commission withholding; the laptop and family travel incentives separately test business benefits/perquisites withholding.'),
        ('Q4.a.iii', 0, [], 'The portal collects auction proceeds and pays a resident seller after commission, explicitly asking its e-commerce TDS obligation.'),
        ('Q4.b.i', 2, [], 'Voting rights, board appointment and guarantees determine associated enterprises for international transfer pricing.'),
        ('Q4.b.ii', 25, [], 'The question explicitly requests the arm-length price using resale margins and comparable consultancy charges.')],
    6: [('Q6.a.ii', 9, [], 'Artificial transfer pricing between SEZ and non-SEZ units to increase deductions explicitly asks whether GAAR applies.'),
        ('Q6.b', 18, [32], 'The task asks whether the ruling board may compel books and admit an application despite another related ruling, testing board powers and receipt procedure.')],
    7: [('Q2.a.i', 12, [29], 'Milling plus fortification under PDS tests composite supply and whether the service is exempt.'),
        ('Q2.a.iv', 29, [], 'Driver training for government with specified funding proportion tests exempt-service conditions.'),
        ('Q2.a.v', 6, [], 'Payment to refrain from building extra floors tests the statutory supply treatment of an obligation to refrain.'),
        ('Q2.b', 13, [], 'The requested taxable value includes job charges and own frames but asks whether principal-owned cabinets belong in consideration.')],
    10: [('*', 5, [], 'All three MCQs require profit/loss and position from premium, strike, spot and exercise/lapse; this is payoff analysis.')],
    19: [('Q2.a', 4, [], 'The non-financial USD equipment host explicitly contains a not-closely-related embedded derivative requiring separate journal accounting.'),
         ('Q2.b', 0, [], 'The task asks current/non-current liability classification after a reporting-date mortgage covenant breach and a lender waiver obtained after statement approval.')],
    20: [('Q4.a.i', 0, [24], 'The shared task requests defined-benefit financial statement reporting, separating service/net-interest cost from remeasurement.'),
         ('Q4.a.ii', 0, [24], 'The shared defined-benefit calculation separates financing cost and actuarial/asset remeasurements.'),
         ('Q4.a.iii', 0, [24], 'The shared task requires defined-benefit cost and OCI remeasurement attribution.'),
         ('Q4.a.iv', 0, [24], 'The pension plan figures are inputs to defined-benefit cost and remeasurements.'),
         ('Q4.a.v', 0, [24], 'The finance-cost instruction and closing plan figures test defined-benefit net interest and remeasurements.'),
         ('Q4.b.i', 2, [], 'The setup incentive asks whether government-grant conditions and receipt justify recognition.'),
         ('Q4.b.ii', 2, [], 'Research and development grant recognition is explicitly requested in the parent task.'),
         ('Q4.b.ii.repeat2', 2, [], 'The three-year employment-conditioned grant explicitly requires recognition based on reasonable assurance and deferred income.')],
    23: [('Q6.a.repeat2', 3, [], 'Adult-son gift versus diversion of earned commission explicitly asks tax planning, management or evasion distinctions.'),
         ('Q6.b', 18, [], 'The task asks whether a pending question with a tax authority bars the ruling board from admitting the nonresident application.')],
}


def main():
    directory = Path('artifacts/phase5')
    manifest = json.loads((directory/'independent30.json').read_text())
    outputs = []
    for index, record in enumerate(manifest['records']):
        mappings = []
        for part_id in record['context']['classification_part_ids']:
            suffix = part_id.split(':', 1)[-1]
            decision = next((d for d in LABELS.get(index, []) if d[0] in (suffix, '*')), None)
            outcome = 'needs_review'
            if index in {12, 24} or index in {7, 25} and '.c.' in suffix:
                outcome = 'none_fits'
            labels = [record['candidates'][i]['node_id'] for i in [decision[1], *decision[2]]] if decision else []
            mappings.append(dict(part_id=part_id, outcome='matched' if decision else outcome,
                primary_node_id=labels[0] if labels else None, secondary_node_ids=labels[1:],
                evidence=[dict(node_id=node, support=decision[3]) for node in labels],
                note=NOTES[index], confidence=None, bucket=None))
        result = dict(question_id=record['question_id'], input_hash=record['input_hash'], mappings=mappings)
        validated_mappings(record, result)
        outputs.append(result)
    result = dict(batch_key=manifest['batch_key'], method='independent_agent', model_id=None,
        model_note='Manually reasoned by Codex classification agent; exact inherited model identifier unavailable.',
        provisional=True, adjudication='No independent student adjudication',
        frozen_before_luna=True, frozen_at=datetime.now(timezone.utc).isoformat(), results=outputs)
    result['digest'] = digest(result)
    target = directory/'independent30_labels.json'
    if target.exists():
        raise RuntimeError('Independent labels are already frozen; do not rewrite after seeing Luna')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'Frozen {len(outputs)} independently reasoned roots, digest {result["digest"]}')


if __name__ == '__main__':
    main()
