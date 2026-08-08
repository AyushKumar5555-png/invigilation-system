import enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional

class ExamType(str, enum.Enum):
    MIDSEM = "midsem"
    ENDSEM = "endsem"

@dataclass
class FacultyCategory:
    name: str  # e.g., "Professor", "Associate Professor", "Assistant Professor"
    ratio_weight: float  # The ratio or weight representing target load multiplier (e.g. 2, 3, 4)

@dataclass
class Faculty:
    id: str
    name: str
    category_name: str  # Must match a category name in the input configuration
    pg_timetable_blocks: List[str] = field(default_factory=list)  # Session IDs (e.g., ["D11", "D32"]) where PG classes conflict
    availability_overrides: List[str] = field(default_factory=list)  # Session IDs (e.g., ["D51"]) where faculty is unavailable
    phone: str = ""

@dataclass
class Session:
    id: str  # e.g., "D11", "D12", ..., "D62"
    day: int  # 1 to 6 (Monday = 1, Saturday = 6)
    session_num: int  # 1 (FN) or 2 (AN)
    label: str  # e.g., "Monday FN"
    required_invigilators: int
    day_weight: float = 1.0  # 1.0 for weekday, 1.5 for Saturday
    duration_hours: float = 2.0  # e.g., 2.0 for midsem, 3.0 for endsem
    start_time: int = 540  # minutes from midnight

@dataclass
class HistoricalRecord:
    faculty_id: str
    previous_imbalance: float  # +n for overload of n hours, -m for underload of m hours, 0 for neutral

@dataclass
class AllocationInput:
    faculty_list: List[Faculty]
    categories: Dict[str, FacultyCategory]
    sessions: List[Session]
    history: List[HistoricalRecord] = field(default_factory=list)
    exam_type: ExamType = ExamType.MIDSEM
    morning_start_time: int = 540
    afternoon_start_time: int = 780

@dataclass
class FacultyReport:
    faculty_id: str
    name: str
    category_name: str
    assigned_sessions: List[str]
    assigned_hours: float
    assigned_weighted_load: float
    target_load: float
    overload: float
    underload: float
    historical_imbalance: float
    cumulative_imbalance: float
    impact_status: str  # "IMPROVED", "WORSENED", or "NEUTRAL"
    selection_explanations: Dict[str, str] = field(default_factory=dict)  # Explanation per assigned session ID

@dataclass
class SessionAllocation:
    session_id: str
    assigned_faculty_ids: List[str]

@dataclass
class AllocationResult:
    success: bool
    schedule: List[SessionAllocation]
    faculty_summaries: List[FacultyReport]
    jains_fairness_index: float
    gini_coefficient: float
    feasibility_report: str
    conflict_report: List[str]
    history_impact_report: str
