"""Classification against reviewed textbook evidence, never legacy labels."""

import re

import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.ref import Paper
from caf_db.models.taxonomy import DescriptorRevision, TaxonomyMember, TaxonomyRelease
from caf_l0.hierarchy import ancestors, version_nodes
from caf_l0.releases import active_version, eligible_candidates
from caf_l3.cascade import ClassificationError, ClassificationResult, generate_concise_gist
from caf_l3.llm import GeminiClassifier


class NeedsTaxonomyReview(ClassificationError):
    """No reviewed textbook concept supports the question."""


class TextbookClassifier:
    def __init__(self, session: Session, version_id: str | None = None,
                 gemini_classifier: GeminiClassifier | None = None):
        self.session = session
        release = session.get(TaxonomyRelease, version_id) if version_id else active_version(session)
        if release is None or release.status == "legacy":
            raise ValueError("A rebuilt taxonomy version is required; review and activate a textbook release or pass its version ID")
        self.release = release
        self.taxonomy_version_id = release.taxonomy_version_id
        self.gemini_classifier = gemini_classifier
        if gemini_classifier:
            gemini_classifier.taxonomy_version_id = self.taxonomy_version_id

    def classify_unit(self, paper_id: str, question_text: str, context_text: str = "",
                      answer_text: str = "", fingerprint: str = "", run_id: int | None = None,
                      use_llm: bool = True, chapter_hint_id: str | None = None) -> ClassificationResult:
        paper = self.session.get(Paper, paper_id)
        if paper is None or paper.scheme_id != "s2023" or not paper.is_current:
            raise ValueError("Classification requires a confirmed current Final paper and scheme")
        # IBS explicitly permits references into the other five papers.
        candidates = eligible_candidates(self.session, self.taxonomy_version_id,
                                         None if paper.code == "P6" else paper_id)
        candidate_map = {candidate.node_id: candidate for candidate in candidates}
        if not candidate_map:
            return ClassificationResult(primary_node_id=None, secondary_node_ids=[],
                bucket='D', method='anchor', outcome='needs_review',
                gist=generate_concise_gist(question_text, answer_text),
                justification='needs taxonomy review: no source-reviewed, descriptor-approved subtopics',
                evidence={'taxonomy_version_id': self.taxonomy_version_id, 'candidate_set': [], 'uncalibrated': True})
        revisions = {}
        for revision in self.session.scalars(sa.select(DescriptorRevision).where(
            DescriptorRevision.taxonomy_version_id == self.taxonomy_version_id,
            DescriptorRevision.node_id.in_(candidate_map),
        ).order_by(DescriptorRevision.revision)):
            revisions[revision.node_id] = revision
        selected = []
        method = "anchor"
        justification = "Matched reviewed descriptor terminology in the complete question and its source context."
        model_id = None
        bucket = "B"  # Local phrase evidence has not been precision-calibrated.
        alternatives = []
        combined = f"{context_text}\n{question_text}\n{answer_text}".casefold()
        if use_llm and self.gemini_classifier and self.gemini_classifier.is_available():
            # Unknown IDs fail explicitly; never substitute a first or historical candidate.
            output = self.gemini_classifier.classify_unit(paper_id, f"{context_text}\n{question_text}",
                                                        answer_text, run_id)
            if output.outcome != 'matched':
                return ClassificationResult(primary_node_id=None, secondary_node_ids=[],
                    bucket=output.bucket, method='llm', outcome=output.outcome,
                    gist=output.gist, justification=output.justification, alternatives=output.alternatives,
                    evidence={'model_id': output.model_id, 'taxonomy_version_id': self.taxonomy_version_id,
                        'candidate_set': list(candidate_map), 'uncalibrated': True})
            selected = list(dict.fromkeys([output.primary_node_id, *output.secondary_node_ids]))
            if not selected or any(node_id not in candidate_map for node_id in selected):
                raise NeedsTaxonomyReview("needs taxonomy review: model selected an unsupported concept")
            method = "llm"
            justification = output.justification
            model_id = output.model_id
            bucket = output.bucket
            alternatives = output.alternatives
        else:
            ranked = []
            for node_id, revision in revisions.items():
                terms = revision.content["terminology"]
                # Phrase/instrument matches supply evidence; generic fuzzy similarity does not.
                matches = [term for term in terms if len(term.strip()) >= 4 and re.search(
                    rf"(?<!\w){re.escape(term.casefold())}(?!\w)", combined
                )]
                exclusions = revision.content.get("exclusion", [])
                excluded = any(re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", combined)
                               for term in exclusions if len(term.strip()) >= 4)
                if matches and not excluded:
                    ranked.append((len(matches), node_id, matches))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            if not ranked:
                return ClassificationResult(primary_node_id=None, secondary_node_ids=[],
                    bucket='D', method='anchor', outcome='none_fits',
                    gist=generate_concise_gist(question_text, answer_text),
                    justification='no supported descriptor terminology matches; human review still required',
                    evidence={'taxonomy_version_id': self.taxonomy_version_id,
                        'candidate_set': list(candidate_map), 'uncalibrated': True})
            # Phrase occurrences retrieve candidates; they do not prove that all
            # mentioned concepts are actually tested. Keep ambiguity unresolved.
            if len(ranked) > 1:
                return ClassificationResult(primary_node_id=None, secondary_node_ids=[],
                    bucket="D", method="anchor", outcome="needs_review",
                    gist=generate_concise_gist(question_text, answer_text),
                    justification="Multiple descriptor matches require explicit tested-concept review.",
                    alternatives=[item[1] for item in ranked], evidence={
                        "taxonomy_version_id": self.taxonomy_version_id,
                        "descriptor_revisions": {node_id: revisions[node_id].id for _, node_id, _ in ranked},
                        "matched_terms": {node_id: terms for _, node_id, terms in ranked},
                        "uncalibrated": True})
            selected = [ranked[0][1]]
        nodes = {node.id: node for node in version_nodes(self.session, self.taxonomy_version_id)}
        evidence = {
            "taxonomy_version_id": self.taxonomy_version_id,
            "version_id": self.release.version_id,
            "descriptor_revisions": {node_id: revisions[node_id].id for node_id in selected},
            "breadcrumbs": {node_id: [
                {"id": node.id, "name": node.name, "level": node.level, "paper_id": node.paper_id}
                for node in ancestors(node_id, nodes)
            ] for node_id in selected},
            "cross_paper_references": [node_id for node_id in selected
                                       if candidate_map[node_id].paper_id != paper_id],
            "model_id": model_id,
            "uncalibrated": True,
            "candidate_set": list(candidate_map),
        }
        if method == "anchor":
            evidence["matched_terms"] = {node_id: terms for _, node_id, terms in ranked}
        else:
            evidence["confidence"] = output.confidence
            evidence["core_tested_concept"] = output.core_tested_concept
            evidence["label_evidence"] = output.label_evidence
        return ClassificationResult(
            primary_node_id=selected[0], secondary_node_ids=selected[1:],
            bucket=bucket, method=method, alternatives=alternatives,
            gist=generate_concise_gist(question_text, answer_text),
            justification=justification, evidence=evidence,
        )
