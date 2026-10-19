"""Resolve shared frozen candidates while retaining historical inline records."""
from sqlalchemy.orm import Session
from caf_db.models.classification import CandidateCatalog, SuggestionRevision


def suggestion_candidates(session: Session, suggestion: SuggestionRevision) -> list[dict]:
    if suggestion.candidate_catalog_hash is None:
        return suggestion.candidates
    catalog = session.get(CandidateCatalog, suggestion.candidate_catalog_hash)
    if catalog is None:
        raise ValueError('Pinned candidate catalog is missing')
    return catalog.candidates
