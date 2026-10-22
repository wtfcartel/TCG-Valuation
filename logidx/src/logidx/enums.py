"""Controlled vocabularies shared by the database, pipeline, AI layer and dashboard."""

from enum import StrEnum


class AccessMethod(StrEnum):
    NATIVE = "NATIVE"  # the source's own public search or employer ATS board
    API = "API"  # an official keyed API
    INDEXED_FALLBACK = "INDEXED_FALLBACK"  # a third-party index (e.g. Google) pointing at the source
    MANUAL = "MANUAL"  # user-supplied / browser-assisted import
    NONE = "NONE"


class SearchStatus(StrEnum):
    NATIVE_SEARCHED = "NATIVE SEARCHED"
    API_SEARCHED = "API SEARCHED"
    INDEXED_FALLBACK_ONLY = "INDEXED FALLBACK ONLY"
    ACCESS_BLOCKED = "ACCESS BLOCKED"
    NOT_SEARCHED = "NOT SEARCHED"
    FAILED = "FAILED"

    @property
    def succeeded(self) -> bool:
        return self in (SearchStatus.NATIVE_SEARCHED, SearchStatus.API_SEARCHED, SearchStatus.INDEXED_FALLBACK_ONLY)


class Verification(StrEnum):
    VERIFIED_OPEN = "VERIFIED OPEN"
    LIKELY_OPEN = "LIKELY OPEN"
    UNVERIFIED_STALE = "UNVERIFIED / STALE"
    RECRUITER_CONFIRMATION = "RECRUITER CONFIRMATION REQUIRED"
    CLOSED = "CLOSED"


class ApplicationStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    SAVED = "SAVED"
    REVIEWING = "REVIEWING"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class Geography(StrEnum):
    MELBOURNE = "MELBOURNE"  # Melbourne metro / Victoria-based
    REGIONAL_VIC = "REGIONAL VIC"  # Victoria outside metro — commute to review
    REMOTE_AU = "REMOTE (AUSTRALIA)"
    NATIONAL_MELBOURNE_OK = "NATIONAL — MELBOURNE OPTION STATED"
    NATIONAL_UNCONFIRMED = "NATIONAL — MELBOURNE NOT CONFIRMED"
    INTERSTATE = "INTERSTATE — RELOCATION OR SUBSTANTIAL ATTENDANCE"
    OVERSEAS = "OVERSEAS"
    UNKNOWN = "UNKNOWN"

    @property
    def melbourne_workable(self) -> bool:
        return self in (Geography.MELBOURNE, Geography.REMOTE_AU, Geography.NATIONAL_MELBOURNE_OK)


class WorkMode(StrEnum):
    ONSITE = "ONSITE"
    HYBRID = "HYBRID"
    REMOTE = "REMOTE"
    UNKNOWN = "UNKNOWN"


class FitClass(StrEnum):
    PRIORITY = "Priority"
    ADJACENT = "Adjacent"
    EXPLORATORY = "Exploratory"
    LOW = "Low relevance"
    UNASSESSED = "Unassessed"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"  # at least one source or category failed
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # duplicate trigger / lock held


class Lifecycle(StrEnum):
    ACTIVE = "ACTIVE"  # seen in the latest successful search of a source that lists it
    NOT_SEEN = "NOT SEEN"  # absent from a successful full listing, inside grace period
    EXPIRED = "EXPIRED"  # absent beyond grace, or closing date passed (record kept)


class RecallOutcome(StrEnum):
    FOUND = "FOUND"
    MISSED = "MISSED"
    ACCESS_GAP = "ACCESS GAP"  # not found and the source that carries it could not be searched


class MissCause(StrEnum):
    SOURCE_ACCESS = "source access"
    QUERY_COVERAGE = "query coverage"
    INDEXING = "indexing"
    FRESHNESS = "freshness"
    LOCATION_FILTERING = "location filtering"
    DEDUPLICATION = "deduplication"
    CLASSIFICATION = "classification"
    UNKNOWN = "unknown"
