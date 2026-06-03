from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Edition(str, Enum):
    OPEN_SOURCE = "open-source"
    SERVER = "server"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    MISSING_BACKEND = "missing_backend"
    MISSING_FRONTEND = "missing_frontend"
    PARAM_MISMATCH = "param_mismatch"
    RESPONSE_MISMATCH = "response_mismatch"
    DYNAMIC_NEEDS_REVIEW = "dynamic_needs_review"
    DEPRECATED = "deprecated"


class StubType(str, Enum):
    PASS = "pass"
    NOT_IMPLEMENTED = "not_implemented"
    EXCEPTION_SWALLOW = "exception_swallow"
    TODO_COMMENT = "todo_comment"
    PLACEHOLDER_TEXT = "placeholder_text"
    EMPTY_COMPONENT = "empty_component"
    MOCK_DATA = "mock_data"


class StubStatus(str, Enum):
    PENDING_IMPLEMENT = "pending_implement"
    PENDING_REMOVE = "pending_remove"
    DEFERRED = "deferred"
    DONE = "done"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class IssueCategory(str, Enum):
    EXCEPTION_SWALLOW = "exception_swallow"
    NO_PYDANTIC = "no_pydantic"
    NO_ERROR_HANDLING = "no_error_handling"
    NO_SUCCESS_FEEDBACK = "no_success_feedback"
    NO_FAILURE_FEEDBACK = "no_failure_feedback"
    NO_CONFIRMATION = "no_confirmation"
    NO_LOADING = "no_loading"
    SILENT_FAILURE = "silent_failure"
    VAGUE_ERROR = "vague_error"
    TECH_JARGON = "tech_jargon"
    NAMING_VIOLATION = "naming_violation"
    HARDCODE = "hardcode"
    MISSING_CONFIG = "missing_config"
    DIRECT_DEPENDENCY = "direct_dependency"
    CODE_DUPLICATION = "code_duplication"
    NO_GLOBAL_HANDLER = "no_global_handler"
    NO_ERROR_BOUNDARY = "no_error_boundary"
    CONFIRM_BYPASSABLE = "confirm_bypassable"
    BATCH_NO_PROGRESS = "batch_no_progress"
    TOO_MANY_STEPS = "too_many_steps"
    LEGACY_NAMING = "legacy_naming"


@dataclass
class RouteInfo:
    method: str
    path: str
    function_name: str
    file_path: str
    line_number: int = 0
    prefix: str = ""
    full_path: str = ""
    has_pydantic: bool = False
    response_model: Optional[str] = None
    is_deprecated: bool = False
    edition_scope: str = "both"
    is_internal: bool = False


@dataclass
class ApiCallInfo:
    method: str
    path: str
    function_name: str = ""
    file_path: str = ""
    line_number: int = 0
    raw_path: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    has_error_handler: bool = False
    has_success_handler: bool = False


@dataclass
class MismatchResult:
    match_status: MatchStatus
    severity: Severity
    direction: str
    method: str
    path: str
    frontend_call: Optional[ApiCallInfo] = None
    backend_route: Optional[RouteInfo] = None
    detail: str = ""
    edition: str = ""


@dataclass
class StubRecord:
    stub_type: StubType
    priority: Priority
    status: StubStatus
    file_path: str
    line_number: int
    description: str
    function_name: str = ""
    edition: str = ""
    defer_deadline: Optional[str] = None


@dataclass
class QualityIssue:
    category: IssueCategory
    severity: Severity
    file_path: str
    line_number: int
    description: str
    current_behavior: str = ""
    expected_behavior: str = ""
    suggestion: str = ""
    edition: str = ""


@dataclass
class ApiConsistencyResult:
    edition: str = ""
    forward_mismatches: list[MismatchResult] = field(default_factory=list)
    reverse_mismatches: list[MismatchResult] = field(default_factory=list)
    total_frontend_calls: int = 0
    total_backend_routes: int = 0
    matched_count: int = 0


@dataclass
class StubScanResult:
    edition: str = ""
    stubs: list[StubRecord] = field(default_factory=list)
    total_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_priority: dict[str, int] = field(default_factory=dict)


@dataclass
class RobustnessResult:
    edition: str = ""
    issues: list[QualityIssue] = field(default_factory=list)
    total_count: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class UsabilityResult:
    edition: str = ""
    issues: list[QualityIssue] = field(default_factory=list)
    total_count: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class UxQualityResult:
    edition: str = ""
    issues: list[QualityIssue] = field(default_factory=list)
    total_count: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class ExtensibilityResult:
    edition: str = ""
    issues: list[QualityIssue] = field(default_factory=list)
    total_count: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class ReportMeta:
    timestamp: str = ""
    project_root: str = ""
    editions_checked: list[str] = field(default_factory=list)
    tool_version: str = "1.0.0"
    total_elapsed_seconds: float = 0.0


@dataclass
class FullCheckReport:
    meta: ReportMeta = field(default_factory=ReportMeta)
    api_consistency: dict[str, ApiConsistencyResult] = field(default_factory=dict)
    stubs: dict[str, StubScanResult] = field(default_factory=dict)
    robustness: dict[str, RobustnessResult] = field(default_factory=dict)
    usability: dict[str, UsabilityResult] = field(default_factory=dict)
    ux_quality: dict[str, UxQualityResult] = field(default_factory=dict)
    extensibility: dict[str, ExtensibilityResult] = field(default_factory=dict)
