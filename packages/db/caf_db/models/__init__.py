"""All SQLAlchemy database models across the 6 schemas."""

from caf_db.models.app import (
    MockTest,
    Note,
    Progress,
    ProgressEvent,
    RevisionEvent,
    Settings,
    StudySession,
    UserAccount,
)
from caf_db.models.base import Base
from caf_db.models.classification import (SuggestionRevision, ClassificationRevision,
    QuestionPublication, ClassificationEvent, ClassificationVerification, ClassificationDispute)
from caf_db.models.extraction import (ExtractionRevision, ContentBlock, ExtractionAsset,
    DocumentPair, ExtractionReview, ReconciliationLink)
from caf_db.models.taxonomy import (TaxonomyRelease, TaxonomyMember, TextbookArtifact,
    NodeSourceSpan, DescriptorRevision, DescriptorApproval, TaxonomyCrosswalk, ProgressMigration)
from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
from caf_db.models.ingest import (
    DiscoveredLink,
    Document,
    DuplicateLink,
    SourcePage,
    TagSuggestion,
    TaxonomyGap,
    Unit,
    UnitAnswer,
    UnitGist,
)
from caf_db.models.intel import DepthGateReport, IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ops import Event, LLMCall, Run
from caf_db.models.ref import (
    Anchor,
    ApplicabilityRule,
    Attempt,
    Descriptor,
    DocType,
    Instrument,
    LawBoundary,
    Node,
    NodeVersionLink,
    Paper,
    Scheme,
    TaxonomyVersion,
    WeightageMember,
    WeightageSection,
)

__all__ = [
    "Anchor",
    "Appearance",
    "AppearanceTag",
    "ApplicabilityRule",
    "Attempt",
    "Base",
    "SuggestionRevision",
    "ClassificationRevision",
    "QuestionPublication",
    "ClassificationEvent",
    "ClassificationVerification",
    "ClassificationDispute",
    "ChangeLog",
    "Decision",
    "DepthGateReport",
    "Descriptor",
    "DiscoveredLink",
    "DocType",
    "Document",
    "DuplicateLink",
    "Event",
    "IngestionCoverage",
    "Instrument",
    "LLMCall",
    "LawBoundary",
    "MockTest",
    "Node",
    "NodeVersionLink",
    "Note",
    "Paper",
    "Progress",
    "ProgressEvent",
    "RevisionEvent",
    "Run",
    "Scheme",
    "ScoreRun",
    "Settings",
    "SourcePage",
    "StudySession",
    "SubtopicScore",
    "TagSuggestion",
    "TaxonomyGap",
    "TaxonomyVersion",
    "Unit",
    "UnitAnswer",
    "UnitGist",
    "UserAccount",
    "WeightageMember",
    "WeightageSection",
]

from caf_db.models.questions import CorpusGeneration, PublishedQuestion, PublishedSource, QuestionOccurrence
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, ReviewedPrior, RecomputeJob
