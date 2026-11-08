from enum import StrEnum

class Role(StrEnum):
    CREATOR = "creator"
    REVIEWER = "reviewer"
    BRAND_OWNER = "brand_owner"
    ADMINISTRATOR = "administrator"

class SubmissionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ANALYSED = "ANALYSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PARSE_FAILED = "PARSE_FAILED"

class ReviewStatus(StrEnum):
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"

class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    CONFLICTING = "CONFLICTING"
    STALE = "STALE"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    INFORMATIONAL = "INFORMATIONAL"

class Severity(StrEnum):
    BLOCKING = "blocking"
    REVIEW_REQUIRED = "review_required"
    SUGGESTION = "suggestion"
    INFORMATIONAL = "informational"

class DecisionAction(StrEnum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"
    OVERRIDE = "OVERRIDE"
