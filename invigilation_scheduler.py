import enum
import time
import json
import sys
import os
import random
import math
import tempfile
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any
from datetime import datetime

# Revert to working gap constraint, confirmed feasible with 0 unfilled slots
# =====================================================================
# 1. DATA MODELS
# =====================================================================

class ExamType(str, enum.Enum):
    MIDSEM = "midsem"
    ENDSEM = "endsem"

@dataclass
class FacultyCategory:
    name: str
    ratio_weight: float

@dataclass
class Faculty:
    id: str
    name: str
    category_name: str
    pg_timetable_blocks: List[str] = field(default_factory=list)
    availability_overrides: List[str] = field(default_factory=list)
    phone: str = ""

@dataclass
class Session:
    id: str
    day: int
    session_num: int
    label: str
    required_invigilators: int
    day_weight: float = 1.0
    duration_hours: float = 2.0
    start_time: int = 540

@dataclass
class HistoricalRecord:
    faculty_id: str
    previous_imbalance: float

@dataclass
class AllocationInput:
    faculty_list: List[Faculty]
    categories: Dict[str, FacultyCategory]
    sessions: List[Session]
    history: List[HistoricalRecord] = field(default_factory=list)
    exam_type: ExamType = ExamType.MIDSEM
    category_ratio_mode: str = "target_load_scaling"
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
    impact_status: str
    selection_explanations: Dict[str, str] = field(default_factory=dict)

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

# =====================================================================
# 2. METRIC CALCULATIONS
# =====================================================================

def calculate_session_weighted_hours(session: Session) -> float:
    return session.duration_hours * session.day_weight

def calculate_total_required_weighted_hours(sessions: List[Session]) -> float:
    total = 0.0
    for s in sessions:
        total += s.required_invigilators * calculate_session_weighted_hours(s)
    return total

def calculate_target_loads(
    faculty_list: List[Faculty],
    categories: Dict[str, FacultyCategory],
    sessions: List[Session],
    ratio_mode: str = "target_load_scaling",
    custom_raw_targets: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    if not faculty_list:
        return {}

    for f in faculty_list:
        if f.category_name not in categories:
            raise ValueError(f"Category '{f.category_name}' for faculty '{f.id}' not found in categories dict.")

    total_required = calculate_total_required_weighted_hours(sessions)

    if ratio_mode in ("target_load_scaling", "hard_category_limits"):
        sum_weights = sum(categories[f.category_name].ratio_weight for f in faculty_list)
        if sum_weights == 0:
            return {f.id: 0.0 for f in faculty_list}
            
        scaling_factor = total_required / sum_weights
        return {f.id: categories[f.category_name].ratio_weight * scaling_factor for f in faculty_list}
        
    elif ratio_mode == "raw_weights":
        if custom_raw_targets is not None:
            return {f.id: custom_raw_targets.get(f.category_name, categories[f.category_name].ratio_weight) for f in faculty_list}
        return {f.id: categories[f.category_name].ratio_weight}
        
    else:
        raise ValueError(f"Unknown ratio_mode: {ratio_mode}")

def calculate_jains_index(loads: List[float], targets: List[float]) -> float:
    n = len(loads)
    if n == 0:
        return 1.0
    
    ratios = []
    for l, t in zip(loads, targets):
        if t > 0:
            ratios.append(l / t)
        else:
            ratios.append(1.0 if l == 0 else 0.0)
            
    sum_ratios = sum(ratios)
    if sum_ratios == 0:
        return 1.0
        
    sum_sq_ratios = sum(x ** 2 for x in ratios)
    return (sum_ratios ** 2) / (n * sum_sq_ratios)

def calculate_gini_coefficient(loads: List[float], targets: List[float]) -> float:
    n = len(loads)
    if n == 0:
        return 0.0
        
    ratios = []
    for l, t in zip(loads, targets):
        if t > 0:
            ratios.append(l / t)
        else:
            ratios.append(1.0 if l == 0 else 2.0)
            
    sum_ratios = sum(ratios)
    if sum_ratios == 0:
        return 0.0
        
    diff_sum = 0.0
    for r_i in ratios:
        for r_j in ratios:
            diff_sum += abs(r_i - r_j)
            
    return diff_sum / (2 * n * sum_ratios)

# =====================================================================
# 3. CORE SCHEDULING SOLVER ENGINE
# =====================================================================

class InvigilationSolver:
    def __init__(self, input_data: AllocationInput, ratio_mode: Optional[str] = None, custom_raw_targets: Optional[Dict[str, float]] = None):
        self.input_data = input_data
        self.ratio_mode = ratio_mode or input_data.category_ratio_mode or "target_load_scaling"
        self.custom_raw_targets = custom_raw_targets
        
        self.categories = input_data.categories
        self.faculty_map = {f.id: f for f in input_data.faculty_list}
        self.faculty_index = {f.id: i for i, f in enumerate(input_data.faculty_list)}
        self.sessions = sorted(input_data.sessions, key=lambda s: (s.day, s.session_num))
        
        self.history_map = {f.id: 0.0 for f in input_data.faculty_list}
        for record in input_data.history:
            if record.faculty_id in self.history_map:
                self.history_map[record.faculty_id] = record.previous_imbalance
                
        self.target_loads = calculate_target_loads(
            faculty_list=input_data.faculty_list,
            categories=self.categories,
            sessions=self.sessions,
            ratio_mode=self.ratio_mode,
            custom_raw_targets=self.custom_raw_targets
        )

        self.faculty_duties = {f.id: {} for f in input_data.faculty_list}
        self.faculty_last_duty_time = {}

    def _add_duty(self, fac_id: str, session: Session):
        self.faculty_duties[fac_id].setdefault(session.day, []).append(session.start_time)
        self.faculty_duties[fac_id][session.day].sort()
        max_day = max(self.faculty_duties[fac_id].keys())
        self.faculty_last_duty_time[fac_id] = (max_day, max(self.faculty_duties[fac_id][max_day]))

    def _remove_duty(self, fac_id: str, session: Session):
        if session.day in self.faculty_duties[fac_id]:
            if session.start_time in self.faculty_duties[fac_id][session.day]:
                self.faculty_duties[fac_id][session.day].remove(session.start_time)
            if not self.faculty_duties[fac_id][session.day]:
                del self.faculty_duties[fac_id][session.day]
        if self.faculty_duties[fac_id]:
            max_day = max(self.faculty_duties[fac_id].keys())
            self.faculty_last_duty_time[fac_id] = (max_day, max(self.faculty_duties[fac_id][max_day]))
        else:
            if fac_id in self.faculty_last_duty_time:
                del self.faculty_last_duty_time[fac_id]

    def _is_faculty_eligible_for_session(self, fac_id: str, session: Session, current_load: float, ignore_pg: bool = False, ignore_overrides: bool = False) -> bool:
        faculty = self.faculty_map[fac_id]
        
        if not ignore_pg and self.input_data.exam_type == ExamType.MIDSEM:
            if session.id in faculty.pg_timetable_blocks:
                return False
                
        if not ignore_overrides and session.id in faculty.availability_overrides:
            return False

        # Same-day: max 2 duties, with 120-minute minimum gap between them
        if session.day in self.faculty_duties[fac_id]:
            existing_times_today = self.faculty_duties[fac_id][session.day]
            if len(existing_times_today) >= 2:
                return False
            for t in existing_times_today:
                if abs(session.start_time - t) < 120:
                    return False

        # Consecutive day gap constraint (120 minutes) — check against LAST duty of previous day and FIRST duty of next day
        if (session.day - 1) in self.faculty_duties[fac_id]:
            prev_day_times = self.faculty_duties[fac_id][session.day - 1]
            if prev_day_times:
                gap = (session.day * 1440 + session.start_time) - ((session.day - 1) * 1440 + max(prev_day_times))
                if gap < 120:
                    return False
        if (session.day + 1) in self.faculty_duties[fac_id]:
            next_day_times = self.faculty_duties[fac_id][session.day + 1]
            if next_day_times:
                gap = ((session.day + 1) * 1440 + min(next_day_times)) - (session.day * 1440 + session.start_time)
                if gap < 120:
                    return False
            
        if self.ratio_mode == "hard_category_limits":
            w_hrs = calculate_session_weighted_hours(session)
            if current_load + w_hrs > self.target_loads[fac_id] + 1e-5:
                return False
                
        return True

    def validate_allocation(self, schedule: List[SessionAllocation]) -> List[str]:
        errors = []
        assigned_slots = {sa.session_id: sa.assigned_faculty_ids for sa in schedule}
        for session in self.sessions:
            assigned_facs = assigned_slots.get(session.id, [])
            if len(assigned_facs) != session.required_invigilators:
                errors.append(
                    f"Session Coverage Violation: Session {session.id} ({session.label}) requires "
                    f"{session.required_invigilators} invigilators, but has {len(assigned_facs)} assigned."
                )
                
        faculty_day_duties: Dict[str, Dict[int, List[str]]] = {}
        faculty_load: Dict[str, float] = {f.id: 0.0 for f in self.input_data.faculty_list}
        faculty_day_times: Dict[str, Dict[int, List[int]]] = {}
        
        for sa in schedule:
            session = next((s for s in self.sessions if s.id == sa.session_id), None)
            if not session:
                continue
            w_hrs = calculate_session_weighted_hours(session)
            for f_id in sa.assigned_faculty_ids:
                faculty = self.faculty_map[f_id]
                faculty_day_duties.setdefault(f_id, {}).setdefault(session.day, []).append(session.id)
                faculty_load[f_id] += w_hrs
                faculty_day_times.setdefault(f_id, {}).setdefault(session.day, []).append(session.start_time)
                
                if self.input_data.exam_type == ExamType.MIDSEM:
                    if session.id in faculty.pg_timetable_blocks:
                        errors.append(
                            f"PG Timetable Conflict: Faculty {faculty.name} ({f_id}) is assigned to "
                            f"Session {session.id} ({session.label}) despite having a PG lecture block."
                        )
                        
                if session.id in faculty.availability_overrides:
                    errors.append(
                        f"Availability Violation: Faculty {faculty.name} ({f_id}) is assigned to "
                        f"Session {session.id} ({session.label}) despite being marked unavailable."
                    )

        for f_id, day_map in faculty_day_times.items():
            for day in day_map:
                day_map[day].sort()
                    
        for f_id, day_map in faculty_day_duties.items():
            faculty = self.faculty_map[f_id]
            for day, sessions in day_map.items():
                if len(sessions) > 2:
                    errors.append(
                        f"Exceeds Max 2 Duties Per Day: Faculty {faculty.name} ({f_id}) is assigned to "
                        f"{len(sessions)} sessions ({', '.join(sessions)}) on Day {day} — maximum allowed is 2."
                    )
                    
        # Same-day and consecutive day minimum gap violations using faculty_day_times
        for f_id, day_map in faculty_day_times.items():
            faculty = self.faculty_map[f_id]
            for day, times in day_map.items():
                # Same-day minimum gap check
                if len(times) > 1:
                    for i in range(len(times) - 1):
                        gap = abs(times[i+1] - times[i])
                        if gap < 120:
                            errors.append(
                                f"Same-Day Minimum Gap Violation: Faculty {faculty.name} ({f_id}) assigned to "
                                f"multiple sessions on Day {day} with gap of only {gap} minutes."
                            )
                # Consecutive day gap check (last duty of day vs first duty of next day)
                if day + 1 in day_map:
                    t1 = max(times)
                    t2 = min(day_map[day + 1])
                    gap = (day + 1) * 1440 + t2 - (day * 1440 + t1)
                    if gap < 120:
                        errors.append(
                             f"Minimum Gap Violation: Faculty {faculty.name} ({f_id}) assigned at time {t1} on Day {day} and time {t2} on Day {day + 1} — gap is only {gap} minutes, minimum required is 120 minutes."
                        )

        if self.ratio_mode == "hard_category_limits":
            for f_id, load in faculty_load.items():
                target = self.target_loads[f_id]
                if load > target + 1e-5:
                    faculty = self.faculty_map[f_id]
                    errors.append(
                        f"Hard Category Limit Violation: Faculty {faculty.name} ({f_id}) assigned load "
                        f"{load:.2f} hrs exceeds their hard target load of {target:.2f} hrs."
                    )
                    
        return errors

    def check_feasibility(self) -> Tuple[bool, str]:
        if not self.input_data.faculty_list:
            return False, "Feasibility Check Failed: No faculty members provided in the input."
        if not self.sessions:
            return False, "Feasibility Check Failed: No exam sessions provided in the input."
            
        for session in self.sessions:
            available_faculty = self._get_available_faculty_for_session(session)
            if len(available_faculty) < session.required_invigilators:
                return False, (
                    f"Feasibility Check Failed: Session {session.id} ({session.label}) requires "
                    f"{session.required_invigilators} invigilators, but only {len(available_faculty)} "
                    f"faculty members are available due to PG class conflicts or availability overrides."
                )
                
        day_sessions: Dict[int, List[Session]] = {}
        for session in self.sessions:
            day_sessions.setdefault(session.day, []).append(session)
            
        for day, sessions_on_day in day_sessions.items():
            day_req = sum(s.required_invigilators for s in sessions_on_day)
            available_on_day: Set[str] = set()
            for session in sessions_on_day:
                available_on_day.update(
                    f.id for f in self._get_available_faculty_for_session(session)
                )
            if len(available_on_day) * 2 < day_req:
                session_labels = ", ".join(s.id for s in sessions_on_day)
                return False, (
                    f"Feasibility Check Failed: Day {day} (sessions: {session_labels}) requires a total "
                    f"of {day_req} invigilators, but only {len(available_on_day)} unique faculty members "
                    f"are available on this day. Each faculty can do at most 2 duties/day."
                )
                
        return True, "Passed basic static feasibility checks."

    def _get_available_faculty_for_session(self, session: Session, ignore_pg: bool = False, ignore_overrides: bool = False) -> List[Faculty]:
        available = []
        for f in self.input_data.faculty_list:
            if not ignore_pg and self.input_data.exam_type == ExamType.MIDSEM:
                if session.id in f.pg_timetable_blocks:
                    continue
            if not ignore_overrides:
                if session.id in f.availability_overrides:
                    continue
            available.append(f)
        return available

    def run_diagnostics(self) -> str:
        if getattr(self, '_diagnostics_running', False):
            return "Diagnostics already in progress — recursion prevented."
        self._diagnostics_running = True
        try:
            import copy
            
            input_no_pg = copy.deepcopy(self.input_data)
            for f in input_no_pg.faculty_list:
                f.pg_timetable_blocks = []
            temp_solver_no_pg = InvigilationSolver(input_no_pg, self.ratio_mode, self.custom_raw_targets)
            is_feas, msg = temp_solver_no_pg.check_feasibility()
            if is_feas:
                res = temp_solver_no_pg.solve(max_steps=5000, run_diag=False)
                if res.success:
                    return (
                        "Infeasibility Cause: PG Timetable Conflicts. "
                        "The schedule becomes feasible if faculty lecture schedules are suspended or ignored."
                    )
    
            input_no_override = copy.deepcopy(self.input_data)
            for f in input_no_override.faculty_list:
                f.availability_overrides = []
            temp_solver_no_override = InvigilationSolver(input_no_override, self.ratio_mode, self.custom_raw_targets)
            is_feas, msg = temp_solver_no_override.check_feasibility()
            if is_feas:
                res = temp_solver_no_override.solve(max_steps=5000, run_diag=False)
                if res.success:
                    return (
                        "Infeasibility Cause: Availability Overrides. "
                        "The schedule becomes feasible if special unavailability requests/overrides are ignored."
                    )
    
            day_sessions: Dict[int, List[Session]] = {}
            for session in self.sessions:
                day_sessions.setdefault(session.day, []).append(session)
            for day, sessions_on_day in day_sessions.items():
                day_req = sum(s.required_invigilators for s in sessions_on_day)
                available_on_day = set()
                for session in sessions_on_day:
                    available_on_day.update(
                        f.id for f in self._get_available_faculty_for_session(session)
                    )
                if len(available_on_day) < day_req:
                    return (
                        f"Infeasibility Cause: At-most-one duty per day constraint. "
                        f"Day {day} requires {day_req} duties, but only {len(available_on_day)} faculty are available. "
                        f"Some faculty members must be assigned multiple duties on Day {day} to cover the exams."
                    )
    
            return (
                "Infeasibility Cause: Multiple interacting constraints (PG conflicts, overrides, and daily duty limits). "
                "The total supply of available faculty hours is insufficient to cover all requested sessions. "
                "Please add more faculty, reduce required invigilators, or lift availability blocks."
            )
        finally:
            self._diagnostics_running = False

    def _get_objective(self, assign_dict: Dict[str, List[str]], load_dict: Dict[str, float]) -> float:
        obj = 0.0
        for f_id in self.target_loads:
            h_f = self.history_map[f_id]
            a_f = load_dict[f_id]
            t_f = self.target_loads[f_id]
            c_f = h_f + a_f - t_f
            obj += c_f ** 2
            
            if abs(h_f) > 1e-5:
                worsening = max(0.0, abs(c_f) - abs(h_f))
                obj += worsening * 100.0
        
        unassigned_count = 0
        for session in self.sessions:
            assigned_count = len(assign_dict.get(session.id, []))
            missing = session.required_invigilators - assigned_count
            unassigned_count += missing
            
        obj += unassigned_count * 100000.0
        return obj

    def _run_greedy_initialization(self) -> Tuple[float, Dict[str, List[str]]]:
        self.faculty_duties = {f.id: {} for f in self.input_data.faculty_list}
        self.faculty_last_duty_time = {}
        
        assignment = {s.id: [] for s in self.sessions}
        faculty_daily_duties = {f.id: {} for f in self.input_data.faculty_list}
        faculty_weighted_load = {f.id: 0.0 for f in self.input_data.faculty_list}
        
        session_avail_counts = []
        for s in self.sessions:
            avail = self._get_available_faculty_for_session(s)
            session_avail_counts.append((s, len(avail)))
        sorted_sessions = [
            x[0] for x in sorted(
                session_avail_counts, 
                key=lambda x: (x[0].day, x[0].session_num, x[1], -x[0].day_weight)
            )
        ]
        
        for session in sorted_sessions:
            available = self._get_available_faculty_for_session(session)
            eligible = [
                f for f in available 
                if faculty_daily_duties[f.id].get(session.day, 0) < 2
                and self._is_faculty_eligible_for_session(f.id, session, faculty_weighted_load[f.id])
            ]
            
            eligible.sort(key=lambda f: self.history_map[f.id] + faculty_weighted_load[f.id] - self.target_loads[f.id])
            
            selected = eligible[:session.required_invigilators]
            assignment[session.id] = [f.id for f in selected]
            
            w_hrs = calculate_session_weighted_hours(session)
            for f in selected:
                faculty_daily_duties[f.id][session.day] = faculty_daily_duties[f.id].get(session.day, 0) + 1
                faculty_weighted_load[f.id] += w_hrs
                self._add_duty(f.id, session)
                
        obj = self._get_objective(assignment, faculty_weighted_load)
        return obj, assignment

    def _run_local_search(self, initial_assignment: Dict[str, List[str]], max_iterations: int = 20000) -> Tuple[float, Dict[str, List[str]]]:
        random.seed(42)
        
        assignment = {s_id: list(facs) for s_id, facs in initial_assignment.items()}
        faculty_daily_duties = {f.id: {} for f in self.input_data.faculty_list}
        faculty_weighted_load = {f.id: 0.0 for f in self.input_data.faculty_list}
        
        self.faculty_duties = {f.id: {} for f in self.input_data.faculty_list}
        self.faculty_last_duty_time = {}
        
        for s_id, facs in assignment.items():
            session = next(s for s in self.sessions if s.id == s_id)
            w_hrs = calculate_session_weighted_hours(session)
            for f_id in facs:
                faculty_daily_duties[f_id][session.day] = faculty_daily_duties[f_id].get(session.day, 0) + 1
                faculty_weighted_load[f_id] += w_hrs
                self._add_duty(f_id, session)
                
        current_obj = self._get_objective(assignment, faculty_weighted_load)
        best_obj = current_obj
        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
        
        for _ in range(max_iterations):
            move_type = random.choice(["swap_faculty", "swap_sessions", "fill_unassigned"])
            
            if move_type == "swap_faculty":
                session = random.choice(self.sessions)
                assigned_facs = assignment[session.id]
                if not assigned_facs:
                    continue
                    
                f1_id = random.choice(assigned_facs)
                f2 = random.choice(self.input_data.faculty_list)
                f2_id = f2.id
                
                if f1_id == f2_id:
                    continue
                if faculty_daily_duties[f2_id].get(session.day, 0) >= 2:
                    continue
                    
                w_hrs = calculate_session_weighted_hours(session)
                
                # Propose swap: temporarily remove f1 to test eligibility of f2
                faculty_weighted_load[f1_id] -= w_hrs
                faculty_daily_duties[f1_id][session.day] -= 1
                if faculty_daily_duties[f1_id][session.day] <= 0:
                    del faculty_daily_duties[f1_id][session.day]
                self._remove_duty(f1_id, session)
                
                if not self._is_faculty_eligible_for_session(f2_id, session, faculty_weighted_load[f2_id]):
                    # Revert f1
                    faculty_weighted_load[f1_id] += w_hrs
                    faculty_daily_duties[f1_id][session.day] = faculty_daily_duties[f1_id].get(session.day, 0) + 1
                    self._add_duty(f1_id, session)
                    continue
                    
                # Assign f2
                faculty_weighted_load[f2_id] += w_hrs
                faculty_daily_duties[f2_id][session.day] = faculty_daily_duties[f2_id].get(session.day, 0) + 1
                self._add_duty(f2_id, session)
                
                new_obj = self._get_objective(assignment, faculty_weighted_load)
                
                if new_obj < current_obj:
                    assigned_facs.remove(f1_id)
                    assigned_facs.append(f2_id)
                    current_obj = new_obj
                    if current_obj < best_obj:
                        best_obj = current_obj
                        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
                else:
                    # Revert f2
                    faculty_weighted_load[f2_id] -= w_hrs
                    faculty_daily_duties[f2_id][session.day] -= 1
                    if faculty_daily_duties[f2_id][session.day] <= 0:
                        del faculty_daily_duties[f2_id][session.day]
                    self._remove_duty(f2_id, session)
                    # Revert f1
                    faculty_weighted_load[f1_id] += w_hrs
                    faculty_daily_duties[f1_id][session.day] = faculty_daily_duties[f1_id].get(session.day, 0) + 1
                    self._add_duty(f1_id, session)
                    
            elif move_type == "swap_sessions":
                s1 = random.choice(self.sessions)
                s2 = random.choice(self.sessions)
                if s1.id == s2.id:
                    continue
                    
                s1_facs = assignment[s1.id]
                s2_facs = assignment[s2.id]
                if not s1_facs or not s2_facs:
                    continue
                    
                f1_id = random.choice(s1_facs)
                f2_id = random.choice(s2_facs)
                if f1_id == f2_id:
                    continue
                    
                w1 = calculate_session_weighted_hours(s1)
                w2 = calculate_session_weighted_hours(s2)
                
                if s2.day != s1.day:
                    if faculty_daily_duties[f1_id].get(s2.day, 0) >= 2:
                        continue
                    if faculty_daily_duties[f2_id].get(s1.day, 0) >= 2:
                        continue
                        
                # Temporarily remove both to check eligibility
                self._remove_duty(f1_id, s1)
                self._remove_duty(f2_id, s2)
                
                if not self._is_faculty_eligible_for_session(f1_id, s2, faculty_weighted_load[f1_id] - w1):
                    self._add_duty(f1_id, s1)
                    self._add_duty(f2_id, s2)
                    continue
                if not self._is_faculty_eligible_for_session(f2_id, s1, faculty_weighted_load[f2_id] - w2):
                    self._add_duty(f1_id, s1)
                    self._add_duty(f2_id, s2)
                    continue
                    
                # Apply new duties
                self._add_duty(f1_id, s2)
                self._add_duty(f2_id, s1)
                
                faculty_weighted_load[f1_id] += w2 - w1
                faculty_weighted_load[f2_id] += w1 - w2
                
                if s1.day != s2.day:
                    faculty_daily_duties[f1_id][s1.day] -= 1
                    if faculty_daily_duties[f1_id][s1.day] <= 0:
                        del faculty_daily_duties[f1_id][s1.day]
                    faculty_daily_duties[f1_id][s2.day] = faculty_daily_duties[f1_id].get(s2.day, 0) + 1
                    
                    faculty_daily_duties[f2_id][s2.day] -= 1
                    if faculty_daily_duties[f2_id][s2.day] <= 0:
                        del faculty_daily_duties[f2_id][s2.day]
                    faculty_daily_duties[f2_id][s1.day] = faculty_daily_duties[f2_id].get(s1.day, 0) + 1
                
                new_obj = self._get_objective(assignment, faculty_weighted_load)
                
                if new_obj < current_obj:
                    s1_facs.remove(f1_id)
                    s1_facs.append(f2_id)
                    s2_facs.remove(f2_id)
                    s2_facs.append(f1_id)
                    current_obj = new_obj
                    if current_obj < best_obj:
                        best_obj = current_obj
                        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
                else:
                    # Revert new duties
                    self._remove_duty(f1_id, s2)
                    self._remove_duty(f2_id, s1)
                    # Restore old duties
                    self._add_duty(f1_id, s1)
                    self._add_duty(f2_id, s2)
                    
                    faculty_weighted_load[f1_id] -= w2 - w1
                    faculty_weighted_load[f2_id] -= w1 - w2
                    
                    if s1.day != s2.day:
                        faculty_daily_duties[f1_id][s1.day] = faculty_daily_duties[f1_id].get(s1.day, 0) + 1
                        faculty_daily_duties[f1_id][s2.day] -= 1
                        if faculty_daily_duties[f1_id][s2.day] <= 0:
                            del faculty_daily_duties[f1_id][s2.day]
                        
                        faculty_daily_duties[f2_id][s2.day] = faculty_daily_duties[f2_id].get(s2.day, 0) + 1
                        faculty_daily_duties[f2_id][s1.day] -= 1
                        if faculty_daily_duties[f2_id][s1.day] <= 0:
                            del faculty_daily_duties[f2_id][s1.day]
                        
            elif move_type == "fill_unassigned":
                session = random.choice(self.sessions)
                assigned_facs = assignment[session.id]
                if len(assigned_facs) >= session.required_invigilators:
                    continue
                    
                f = random.choice(self.input_data.faculty_list)
                f_id = f.id
                
                if f_id in assigned_facs:
                    continue
                if faculty_daily_duties[f_id].get(session.day, 0) >= 2:
                    continue
                    
                w_hrs = calculate_session_weighted_hours(session)
                
                if not self._is_faculty_eligible_for_session(f_id, session, faculty_weighted_load[f_id]):
                    continue
                    
                faculty_weighted_load[f_id] += w_hrs
                faculty_daily_duties[f_id][session.day] = faculty_daily_duties[f_id].get(session.day, 0) + 1
                self._add_duty(f_id, session)
                
                new_obj = self._get_objective(assignment, faculty_weighted_load)
                
                if new_obj < current_obj:
                    assigned_facs.append(f_id)
                    current_obj = new_obj
                    if current_obj < best_obj:
                        best_obj = current_obj
                        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
                else:
                    faculty_weighted_load[f_id] -= w_hrs
                    faculty_daily_duties[f_id][session.day] -= 1
                    if faculty_daily_duties[f_id][session.day] <= 0:
                        del faculty_daily_duties[f_id][session.day]
                    self._remove_duty(f_id, session)
                    
        return best_obj, best_assignment

    def solve(self, max_steps: int = 100000, run_diag: bool = True) -> AllocationResult:
        # Feasibility check abort
        is_feas, msg = self.check_feasibility()
        if not is_feas:
            diag = self.run_diagnostics() if run_diag else "Diagnostics bypassed."
            return AllocationResult(
                success=False,
                schedule=[SessionAllocation(session_id=s.id, assigned_faculty_ids=[]) for s in self.sessions],
                faculty_summaries=[
                    FacultyReport(
                        faculty_id=f.id,
                        name=f.name,
                        category_name=f.category_name,
                        assigned_sessions=[],
                        assigned_hours=0.0,
                        assigned_weighted_load=0.0,
                        target_load=self.target_loads.get(f.id, 0.0),
                        overload=0.0,
                        underload=self.target_loads.get(f.id, 0.0),
                        historical_imbalance=self.history_map.get(f.id, 0.0),
                        cumulative_imbalance=self.history_map.get(f.id, 0.0),
                        impact_status="NEUTRAL",
                        selection_explanations={}
                    ) for f in self.input_data.faculty_list
                ],
                jains_fairness_index=calculate_jains_index([0.0 for f in self.input_data.faculty_list], [self.target_loads.get(f.id, 0.0) for f in self.input_data.faculty_list]),
                gini_coefficient=calculate_gini_coefficient([0.0 for f in self.input_data.faculty_list], [self.target_loads.get(f.id, 0.0) for f in self.input_data.faculty_list]),
                feasibility_report="INFEASIBLE",
                conflict_report=[f"Static Feasibility Check Failed: {msg}", f"Diagnostics: {diag}"],
                history_impact_report="No allocation performed due to infeasibility."
            )

        from ortools.sat.python import cp_model
        import time

        model = cp_model.CpModel()

        # 1. Create variables
        x = {}
        for f in self.input_data.faculty_list:
            for s in self.sessions:
                x[f.id, s.id] = model.NewBoolVar(f'x_{f.id}_{s.id}')

        # 2. Hard constraints
        # Exactly required coverage
        for s in self.sessions:
            model.Add(sum(x[f.id, s.id] for f in self.input_data.faculty_list) == s.required_invigilators)

        # Max 2 duties per day
        sessions_by_day = {}
        for s in self.sessions:
            sessions_by_day.setdefault(s.day, []).append(s)

        for f in self.input_data.faculty_list:
            for day, day_sessions in sessions_by_day.items():
                model.Add(sum(x[f.id, s.id] for s in day_sessions) <= 2)

        # PG blocks and availability overrides
        for f in self.input_data.faculty_list:
            if self.input_data.exam_type == ExamType.MIDSEM:
                for block_sess_id in f.pg_timetable_blocks:
                    if (f.id, block_sess_id) in x:
                        model.Add(x[f.id, block_sess_id] == 0)
            for override_sess_id in f.availability_overrides:
                if (f.id, override_sess_id) in x:
                    model.Add(x[f.id, override_sess_id] == 0)

        # Same-day 120-minute gap constraint
        for f in self.input_data.faculty_list:
            for day, day_sessions in sessions_by_day.items():
                n_ds = len(day_sessions)
                for i in range(n_ds):
                    for j in range(i + 1, n_ds):
                        s1 = day_sessions[i]
                        s2 = day_sessions[j]
                        if abs(s1.start_time - s2.start_time) < 120:
                            model.Add(x[f.id, s1.id] + x[f.id, s2.id] <= 1)

        # Consecutive day 120-minute gap constraint
        for f in self.input_data.faculty_list:
            for d in sessions_by_day:
                if d + 1 in sessions_by_day:
                    for s1 in sessions_by_day[d]:
                        for s2 in sessions_by_day[d+1]:
                            gap = (s2.day * 1440 + s2.start_time) - (s1.day * 1440 + s1.start_time)
                            if gap < 120:
                                model.Add(x[f.id, s1.id] + x[f.id, s2.id] <= 1)

        # 3. Objective: minimize total squared deviation (linearized using absolute deviation)
        # Scale factor for floating point hours
        scale = 1000
        dev_vars = []
        for f in self.input_data.faculty_list:
            target_net_scaled = int(round((self.target_loads.get(f.id, 0.0) - self.history_map.get(f.id, 0.0)) * scale))
            assigned_load_scaled_expr = sum(x[f.id, s.id] * int(round(calculate_session_weighted_hours(s) * scale)) for s in self.sessions)
            
            # Absolute deviation variable dev_f
            dev_f = model.NewIntVar(0, 1000000, f'dev_{f.id}')
            model.Add(dev_f >= assigned_load_scaled_expr - target_net_scaled)
            model.Add(dev_f >= target_net_scaled - assigned_load_scaled_expr)
            dev_vars.append(dev_f)

        model.Minimize(sum(dev_vars))

        # 4. Solver parameters & solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        solver.parameters.num_search_workers = 8
        
        start_solve_time = time.time()
        status = solver.Solve(model)
        solve_duration = time.time() - start_solve_time
        
        success = (status == cp_model.OPTIMAL or status == cp_model.FEASIBLE)
        
        best_assignment = {s.id: [] for s in self.sessions}
        faculty_weighted_load = {f.id: 0.0 for f in self.input_data.faculty_list}
        self.faculty_duties = {f.id: {} for f in self.input_data.faculty_list}
        self.faculty_last_duty_time = {}
        
        if success:
            for f in self.input_data.faculty_list:
                for s in self.sessions:
                    if solver.Value(x[f.id, s.id]) > 0.5:
                        best_assignment[s.id].append(f.id)
                        faculty_weighted_load[f.id] += calculate_session_weighted_hours(s)
                        self._add_duty(f.id, s)
        else:
            diag = self.run_diagnostics() if run_diag else "Diagnostics bypassed."
            return AllocationResult(
                success=False,
                schedule=[SessionAllocation(session_id=s.id, assigned_faculty_ids=[]) for s in self.sessions],
                faculty_summaries=[
                    FacultyReport(
                        faculty_id=f.id,
                        name=f.name,
                        category_name=f.category_name,
                        assigned_sessions=[],
                        assigned_hours=0.0,
                        assigned_weighted_load=0.0,
                        target_load=self.target_loads.get(f.id, 0.0),
                        overload=0.0,
                        underload=self.target_loads.get(f.id, 0.0),
                        historical_imbalance=self.history_map.get(f.id, 0.0),
                        cumulative_imbalance=self.history_map.get(f.id, 0.0),
                        impact_status="NEUTRAL",
                        selection_explanations={}
                    ) for f in self.input_data.faculty_list
                ],
                jains_fairness_index=0.0,
                gini_coefficient=0.0,
                feasibility_report="INFEASIBLE",
                conflict_report=[f"CP-SAT solver failed to find a feasible solution. Status: {status}", f"Diagnostics: {diag}"],
                history_impact_report="No allocation performed due to infeasibility."
            )
        
        schedule = [
            SessionAllocation(session_id=s_id, assigned_faculty_ids=facs)
            for s_id, facs in best_assignment.items()
        ]
        
        final_loads = {f.id: 0.0 for f in self.input_data.faculty_list}
        final_hours = {f.id: 0.0 for f in self.input_data.faculty_list}
        final_sessions = {f.id: [] for f in self.input_data.faculty_list}
        
        for s_alloc in schedule:
            session = next(s for s in self.sessions if s.id == s_alloc.session_id)
            w_hrs = calculate_session_weighted_hours(session)
            for f_id in s_alloc.assigned_faculty_ids:
                final_loads[f_id] += w_hrs
                final_hours[f_id] += session.duration_hours
                final_sessions[f_id].append(session.id)
                
        # Sanity check / assertion confirming monotonically non-decreasing (day, session_num) order
        for idx in range(len(schedule) - 1):
            s_curr = next(s for s in self.sessions if s.id == schedule[idx].session_id)
            s_next = next(s for s in self.sessions if s.id == schedule[idx + 1].session_id)
            assert (s_curr.day, s_curr.session_num) <= (s_next.day, s_next.session_num), "Schedule ordering regression detected!"

        validation_errors = self.validate_allocation(schedule)
        
        coverage_errors = [e for e in validation_errors if "Coverage" in e]
        hard_limit_errors = [e for e in validation_errors if "Hard Category Limit" in e]
        other_errors = [e for e in validation_errors if "Coverage" not in e and "Hard Category Limit" not in e]
        
        if other_errors or coverage_errors:
            feasibility_status = "INFEASIBLE"
            success = False
        else:
            feasibility_status = "FEASIBLE"
            success = True
            
        diagnostic_report = []
        if other_errors:
            diagnostic_report.extend(other_errors)
        if hard_limit_errors:
            diagnostic_report.extend(hard_limit_errors)
        if coverage_errors:
            unfilled_sessions = []
            for sa in schedule:
                session = next(s for s in self.sessions if s.id == sa.session_id)
                if len(sa.assigned_faculty_ids) < session.required_invigilators:
                    unfilled_sessions.append(session.id)
                    available_facs = self._get_available_faculty_for_session(session)
                    fac_names = [f.name for f in available_facs]
                    diagnostic_report.append(
                        f" - Session {session.id} ({session.label}) has {len(sa.assigned_faculty_ids)} "
                        f"assigned out of {session.required_invigilators} required. "
                        f"Available unique faculty for this session: {', '.join(fac_names) if fac_names else 'None'}"
                    )
            if run_diag:
                relaxation_source = self.run_diagnostics()
                diagnostic_report.append(f"Diagnostics: {relaxation_source}")

        faculty_summaries: List[FacultyReport] = []
        worsened_count = 0
        improved_count = 0
        neutral_count = 0
        
        for f in self.input_data.faculty_list:
            h_f = self.history_map[f.id]
            a_f = final_loads[f.id]
            t_f = self.target_loads[f.id]
            c_f = h_f + a_f - t_f
            
            overload = max(0.0, a_f - t_f)
            underload = max(0.0, t_f - a_f)
            
            if abs(c_f) < abs(h_f):
                impact_status = "IMPROVED"
                improved_count += 1
            elif abs(c_f) > abs(h_f):
                impact_status = "WORSENED"
                worsened_count += 1
            else:
                impact_status = "NEUTRAL"
                neutral_count += 1
                
            explanations = {}
            for s_id in final_sessions[f.id]:
                sess = next(s for s in self.sessions if s.id == s_id)
                reason_parts = []
                if h_f < 0:
                    reason_parts.append(f"Compensated for historical underload of {h_f:+.1f} hrs")
                elif h_f > 0:
                    reason_parts.append(f"Assigned despite historical overload of {h_f:+.1f} hrs")
                else:
                    reason_parts.append("Historically balanced")
                    
                if sess.day_weight > 1.0:
                    reason_parts.append(f"Saturday assignment (weight {sess.day_weight:.1f})")
                else:
                    reason_parts.append("Weekday assignment (weight 1.0)")
                    
                explanations[s_id] = ". ".join(reason_parts)
                
            faculty_summaries.append(
                FacultyReport(
                    faculty_id=f.id,
                    name=f.name,
                    category_name=f.category_name,
                    assigned_sessions=final_sessions[f.id],
                    assigned_hours=final_hours[f.id],
                    assigned_weighted_load=a_f,
                    target_load=t_f,
                    overload=overload,
                    underload=underload,
                    historical_imbalance=h_f,
                    cumulative_imbalance=c_f,
                    impact_status=impact_status,
                    selection_explanations=explanations
                )
            )
            
        loads_list = [final_loads[f.id] for f in self.input_data.faculty_list]
        targets_list = [self.target_loads[f.id] for f in self.input_data.faculty_list]
        
        jains = calculate_jains_index(loads_list, targets_list)
        gini = calculate_gini_coefficient(loads_list, targets_list)
        
        history_report = (
            f"History Impact Analysis: Out of {len(self.input_data.faculty_list)} faculty members, "
            f"{improved_count} improved their load balance, "
            f"{worsened_count} worsened, and {neutral_count} remained unchanged."
        )
        
        return AllocationResult(
            success=success,
            schedule=schedule,
            faculty_summaries=faculty_summaries,
            jains_fairness_index=jains,
            gini_coefficient=gini,
            feasibility_report=feasibility_status,
            conflict_report=diagnostic_report,
            history_impact_report=history_report
        )

    def get_weekly_grid(self, result: AllocationResult, input_data: AllocationInput) -> Dict:
        day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
        grid = {}
        for d in range(1, 7):
            grid[str(d)] = {
                "Morning": [],
                "Afternoon": []
            }
        
        alloc_map = {sa.session_id: sa.assigned_faculty_ids for sa in result.schedule}
        
        for s in input_data.sessions:
            day_str = str(s.day)
            shift_name = "Morning" if s.session_num == 1 else "Afternoon"
            if day_str not in grid:
                grid[day_str] = {"Morning": [], "Afternoon": []}
            if shift_name not in grid[day_str]:
                grid[day_str][shift_name] = []
                
            fac_ids = alloc_map.get(s.id, [])
            assigned_fac_list = []
            for f_id in fac_ids:
                faculty = self.faculty_map.get(f_id)
                if faculty:
                    assigned_fac_list.append({
                        "id": faculty.id,
                        "name": faculty.name,
                        "category": faculty.category_name
                    })
            
            grid[day_str][shift_name].append({
                "session_id": s.id,
                "label": s.label,
                "required_invigilators": s.required_invigilators,
                "assigned_faculty": assigned_fac_list
            })
        return grid

    def get_faculty_weekly_report(self, faculty_id: str, result: AllocationResult, input_data: AllocationInput) -> Dict:
        report = next((r for r in result.faculty_summaries if r.faculty_id == faculty_id), None)
        if not report:
            return {}
        
        day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
        
        assigned_sessions_info = []
        for s_id in report.assigned_sessions:
            s = next((sess for sess in input_data.sessions if sess.id == s_id), None)
            if s:
                shift_name = "Morning" if s.session_num == 1 else "Afternoon"
                assigned_sessions_info.append({
                    "session_id": s.id,
                    "day_num": s.day,
                    "day_name": day_names.get(s.day, f"Day {s.day}"),
                    "shift": shift_name,
                    "label": s.label,
                    "start_time": s.start_time,
                    "start_time_display": f"{s.start_time // 60:02d}:{s.start_time % 60:02d}",
                    "duration_hours": s.duration_hours
                })
        
        return {
            "faculty_id": report.faculty_id,
            "name": report.name,
            "category_name": report.category_name,
            "assigned_sessions": assigned_sessions_info,
            "assigned_hours": report.assigned_hours,
            "assigned_weighted_load": report.assigned_weighted_load,
            "target_load": report.target_load,
            "cumulative_imbalance": report.cumulative_imbalance,
            "impact_status": report.impact_status
        }

# =====================================================================
# 4. CONFIGURATION LOADER & STATE PERSISTENCE
# =====================================================================

def load_from_dict(data: Dict[str, Any]) -> AllocationInput:
    exam_type_str = data.get("exam_type", "midsem").lower()
    exam_type = ExamType.MIDSEM if exam_type_str == "midsem" else ExamType.ENDSEM
    
    categories_raw = data.get("categories", {})
    categories: Dict[str, FacultyCategory] = {}
    
    if isinstance(categories_raw, list):
        for cat in categories_raw:
            name = cat["name"]
            weight = float(cat.get("ratio_weight", 1.0))
            categories[name] = FacultyCategory(name=name, ratio_weight=weight)
    elif isinstance(categories_raw, dict):
        for name, weight in categories_raw.items():
            if isinstance(weight, dict):
                w_val = float(weight.get("ratio_weight", 1.0))
            else:
                w_val = float(weight)
            categories[name] = FacultyCategory(name=name, ratio_weight=w_val)
    else:
        raise ValueError("Categories must be a list or dictionary.")

    faculty_list_raw = data.get("faculty_list", [])
    faculty_list: List[Faculty] = []
    for f in faculty_list_raw:
        fac_id = f["id"]
        fac_name = f.get("name", fac_id)
        cat_name = f.get("category", f.get("category_name"))
        pg_blocks = f.get("pg_timetable_blocks", [])
        overrides = f.get("availability_overrides", [])
        
        faculty_list.append(
            Faculty(
                id=fac_id,
                name=fac_name,
                category_name=cat_name,
                pg_timetable_blocks=pg_blocks,
                availability_overrides=overrides,
                phone=f.get("phone", "")
            )
        )

    default_duration = 2.0 if exam_type == ExamType.MIDSEM else 3.0

    morning_start = int(data.get("morning_start_time", 540))
    afternoon_start = int(data.get("afternoon_start_time", 780))

    sessions_raw = data.get("sessions", [])
    sessions: List[Session] = []
    for s in sessions_raw:
        s_id = s.get("id")
        if not s_id:
            continue
            
        day_val = s.get("day")
        if day_val is None:
            print(f"WARNING: Skipping session {s_id} because 'day' is missing or null.")
            continue
        try:
            day = int(day_val)
        except (ValueError, TypeError):
            print(f"WARNING: Skipping session {s_id} because 'day' value {day_val} is invalid.")
            continue
            
        sess_num_val = s.get("session_num")
        if sess_num_val is None:
            print(f"WARNING: 'session_num' is missing/null for session {s_id}, defaulting to 1.")
            sess_num = 1
        else:
            try:
                sess_num = int(sess_num_val)
            except (ValueError, TypeError):
                print(f"WARNING: Invalid 'session_num' {sess_num_val} for session {s_id}, defaulting to 1.")
                sess_num = 1
                
        label = s.get("label", f"Day {day} Session {sess_num}")
        
        req_inv_val = s.get("required_invigilators")
        if req_inv_val is None:
            # Fallback to the same value as the other shift that day
            other_shift_val = None
            for other_s in sessions_raw:
                if other_s.get("id") != s_id and other_s.get("day") == day_val and other_s.get("required_invigilators") is not None:
                    other_shift_val = other_s.get("required_invigilators")
                    break
            if other_shift_val is not None:
                try:
                    req_inv = int(other_shift_val)
                    print(f"WARNING: 'required_invigilators' is missing/null for session {s_id}, defaulting to other shift value: {req_inv}.")
                except (ValueError, TypeError):
                    req_inv = 15
                    print(f"WARNING: 'required_invigilators' is missing/null for session {s_id}, fallback default: 15.")
            else:
                req_inv = 15
                print(f"WARNING: 'required_invigilators' is missing/null for session {s_id}, fallback default: 15.")
        else:
            try:
                req_inv = int(req_inv_val)
            except (ValueError, TypeError):
                req_inv = 15
                print(f"WARNING: Invalid 'required_invigilators' {req_inv_val} for session {s_id}, defaulting to 15.")
        
        default_day_weight = 1.5 if day == 6 else 1.0
        day_weight = float(s.get("day_weight", default_day_weight))
        duration = float(s.get("duration_hours", default_duration))
        
        start_time = s.get("start_time")
        if start_time is None:
            start_time = morning_start if sess_num == 1 else afternoon_start
        else:
            try:
                start_time = int(start_time)
            except (ValueError, TypeError):
                start_time = morning_start if sess_num == 1 else afternoon_start
            
        sessions.append(
            Session(
                id=s_id,
                day=day,
                session_num=sess_num,
                label=label,
                required_invigilators=req_inv,
                day_weight=day_weight,
                duration_hours=duration,
                start_time=start_time
            )
        )

    history_raw = data.get("history", [])
    history: List[HistoricalRecord] = []
    
    if isinstance(history_raw, list):
        for h in history_raw:
            f_id = h["faculty_id"]
            val = float(h.get("previous_imbalance", 0.0))
            history.append(HistoricalRecord(faculty_id=f_id, previous_imbalance=val))
    elif isinstance(history_raw, dict):
        for f_id, val in history_raw.items():
            history.append(HistoricalRecord(faculty_id=f_id, previous_imbalance=float(val)))

    ratio_mode = data.get("category_ratio_mode", "target_load_scaling")

    return AllocationInput(
        faculty_list=faculty_list,
        categories=categories,
        sessions=sessions,
        history=history,
        exam_type=exam_type,
        category_ratio_mode=ratio_mode,
        morning_start_time=morning_start,
        afternoon_start_time=afternoon_start
    )

def load_from_json(json_str: str) -> AllocationInput:
    data = json.loads(json_str)
    return load_from_dict(data)

def save_state_transactional(file_path: str, data: Dict[str, Any]):
    dir_name = os.path.dirname(file_path)
    if not dir_name:
        dir_name = "."
    fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        if os.path.exists(file_path):
            os.replace(temp_path, file_path)
        else:
            os.rename(temp_path, file_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

# =====================================================================
# 5. CLI RUNNER LOGIC & EXPLANATIONS
# =====================================================================

def reconfigure_sessions_to_2_shifts(input_data: AllocationInput):
    day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    new_sessions = []
    for s in input_data.sessions:
        if s.session_num > 2:
            continue
        day_name = day_names.get(s.day, f"Day {s.day}")
        if s.session_num == 1:
            s.label = f"{day_name} Morning"
            s.start_time = input_data.morning_start_time
        elif s.session_num == 2:
            s.label = f"{day_name} Afternoon"
            s.start_time = input_data.afternoon_start_time
        new_sessions.append(s)
    input_data.sessions = new_sessions

def explain_worsening(summary: FacultyReport, input_data: AllocationInput, schedule: List[SessionAllocation]) -> str:
    h_f = summary.historical_imbalance
    c_f = summary.cumulative_imbalance
    
    if abs(c_f) <= abs(h_f):
        return "N/A (Imbalance improved or remained unchanged)"
        
    if h_f == 0:
        return "Previously perfectly balanced (0.0). Since the exam required duties to cover all sessions, any assignment deviates from 0.0."
        
    reasons = []
    for s_id in summary.assigned_sessions:
        session = next((s for s in input_data.sessions if s.id == s_id), None)
        if not session:
            continue
            
        other_facs = [fac for fac in input_data.faculty_list if fac.id != summary.faculty_id]
        
        available_others = []
        blocked_by_pg = []
        blocked_by_override = []
        for fac in other_facs:
            if input_data.exam_type == ExamType.MIDSEM and session.id in fac.pg_timetable_blocks:
                blocked_by_pg.append(fac.name)
            elif session.id in fac.availability_overrides:
                blocked_by_override.append(fac.name)
            else:
                available_others.append(fac)
                
        assigned_others_on_day = []
        for sa in schedule:
            if sa.session_id == session.id:
                continue
            curr_sess = next((s for s in input_data.sessions if s.id == sa.session_id), None)
            if curr_sess and curr_sess.day == session.day:
                for assigned_id in sa.assigned_faculty_ids:
                    matched = next((fac for fac in available_others if fac.id == assigned_id), None)
                    if matched:
                        assigned_others_on_day.append(matched.name)
                        break
                        
        eligible_others = [fac for fac in available_others if fac.name not in assigned_others_on_day]
        
        if len(eligible_others) < session.required_invigilators:
            details = []
            if blocked_by_pg:
                details.append(f"{len(blocked_by_pg)} PG conflicts")
            if blocked_by_override:
                details.append(f"{len(blocked_by_override)} overrides")
            if assigned_others_on_day:
                details.append(f"{len(assigned_others_on_day)} assigned on same day")
            reasons.append(f"Session {session.id} ({session.label}): shortage of other eligible faculty (" + ", ".join(details) + ")")
            
    if not reasons:
        return "Assigned to balance category ratio requirements and overall department load."
    return "Required on specific days due to constraints: " + "; ".join(reasons)

SAMPLE_DATA = {
    "exam_type": "midsem",
    "category_ratio_mode": "target_load_scaling",
    "categories": [
        {"name": "Professor", "ratio_weight": 2.0},
        {"name": "Associate Professor", "ratio_weight": 3.0},
        {"name": "Assistant Professor", "ratio_weight": 4.0}
    ],
    "faculty_list": [
        {"id": "P1", "name": "Prof. P1", "category": "Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "P2", "name": "Prof. P2", "category": "Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AS1", "name": "Assoc Prof. AS1", "category": "Associate Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AS2", "name": "Assoc Prof. AS2", "category": "Associate Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AS3", "name": "Assoc Prof. AS3", "category": "Associate Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AP1", "name": "Asst Prof. AP1", "category": "Assistant Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AP2", "name": "Asst Prof. AP2", "category": "Assistant Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AP3", "name": "Asst Prof. AP3", "category": "Assistant Professor", "pg_timetable_blocks": [], "availability_overrides": []},
        {"id": "AP4", "name": "Asst Prof. AP4", "category": "Assistant Professor", "pg_timetable_blocks": [], "availability_overrides": []}
    ],
    "sessions": [
        {"id": "D11", "day": 1, "session_num": 1, "label": "Monday FN", "required_invigilators": 4},
        {"id": "D12", "day": 1, "session_num": 2, "label": "Monday AN", "required_invigilators": 3},
        {"id": "D21", "day": 2, "session_num": 1, "label": "Tuesday FN", "required_invigilators": 3},
        {"id": "D22", "day": 2, "session_num": 2, "label": "Tuesday AN", "required_invigilators": 3},
        {"id": "D31", "day": 3, "session_num": 1, "label": "Wednesday FN", "required_invigilators": 2},
        {"id": "D32", "day": 3, "session_num": 2, "required_invigilators": 4},
        {"id": "D41", "day": 4, "session_num": 1, "label": "Thursday FN", "required_invigilators": 3},
        {"id": "D42", "day": 4, "session_num": 2, "required_invigilators": 2},
        {"id": "D51", "day": 5, "session_num": 1, "label": "Friday FN", "required_invigilators": 2},
        {"id": "D52", "day": 5, "session_num": 2, "required_invigilators": 2},
        {"id": "D61", "day": 6, "session_num": 1, "required_invigilators": 2, "day_weight": 1.5},
        {"id": "D62", "day": 6, "session_num": 2, "required_invigilators": 1, "day_weight": 1.5}
    ],
    "history": [
        {"faculty_id": "P1", "previous_imbalance": 0.0},
        {"faculty_id": "P2", "previous_imbalance": 0.0},
        {"faculty_id": "AS1", "previous_imbalance": 0.0},
        {"faculty_id": "AS2", "previous_imbalance": 0.0},
        {"faculty_id": "AS3", "previous_imbalance": 0.0},
        {"faculty_id": "AP1", "previous_imbalance": 0.0},
        {"faculty_id": "AP2", "previous_imbalance": 0.0},
        {"faculty_id": "AP3", "previous_imbalance": 0.0},
        {"faculty_id": "AP4", "previous_imbalance": 0.0}
    ]
}

def print_report(result: AllocationResult, input_data: AllocationInput):
    print("=" * 100)
    print("                      UNIVERSITY INVIGILATION DUTY ALLOCATION REPORT")
    print("=" * 100)
    print(f"Feasibility Status:     {result.feasibility_report}")
    print(f"Jain's Fairness Index:  {result.jains_fairness_index:.4f} (1.0 is perfectly equal/fair)")
    print(f"Gini Coefficient:       {result.gini_coefficient:.4f} (0.0 is perfect equality)")
    print("-" * 100)
    
    print("\nDAY-WISE ALLOCATION SCHEDULE")
    print("-" * 100)
    header = f"{'Session':<10} | {'Day':<4} | {'Label':<15} | {'Req':<4} | {'Assigned Faculty'}"
    print(header)
    print("-" * 100)
    
    id_to_fac_name = {f.id: f.name for f in input_data.faculty_list}
    
    for sess_alloc in result.schedule:
        sess = next(s for s in input_data.sessions if s.id == sess_alloc.session_id)
        fac_names = [id_to_fac_name[f_id] for f_id in sess_alloc.assigned_faculty_ids]
        
        missing_count = sess.required_invigilators - len(sess_alloc.assigned_faculty_ids)
        if missing_count > 0:
            fac_names.append(f"({missing_count} UNASSIGNED SLOTS)")
            
        fac_str = ", ".join(fac_names)
        print(f"{sess.id:<10} | Day {sess.day:<2} | {sess.label:<15} | {sess.required_invigilators:<4} | {fac_str}")
    print("-" * 100)
    
    print("\nFACULTY WORKLOAD SUMMARY")
    print("-" * 100)
    fac_header = (
        f"{'Faculty ID':<10} | {'Name':<15} | {'Category':<15} | "
        f"{'Duties':<6} | {'Hours':<6} | {'W_Load':<7} | {'Target':<7} | {'Imbalance':<9} | {'Status'}"
    )
    print(fac_header)
    print("-" * 100)
    
    for summary in sorted(result.faculty_summaries, key=lambda s: s.faculty_id):
        duties_count = len(summary.assigned_sessions)
        imb_str = f"{summary.cumulative_imbalance:+.2f}"
        print(
            f"{summary.faculty_id:<10} | {summary.name:<15} | {summary.category_name:<15} | "
            f"{duties_count:<6} | {summary.assigned_hours:<6.1f} | "
            f"{summary.assigned_weighted_load:<7.2f} | {summary.target_load:<7.2f} | "
            f"{imb_str:<9} | {summary.impact_status}"
        )
    print("-" * 100)
    print(result.history_impact_report)
    print("-" * 100)
    
    if not result.success or "PARTIAL" in result.feasibility_report:
        print("\nDIAGNOSTIC & CONFLICT REPORT")
        print("-" * 100)
        for line in result.conflict_report:
            print(f"  - {line}")
        print("-" * 100)
        
    worsened_reports = [s for s in result.faculty_summaries if s.impact_status == "WORSENED"]
    if worsened_reports:
        print("\nHISTORICAL IMBALANCE WORSENING EXPLANATIONS")
        print("-" * 100)
        print(f"{'Faculty ID':<10} | {'Name':<15} | {'Imbalance':<9} | {'Justification / Explanation'}")
        print("-" * 100)
        for summary in worsened_reports:
            explanation = explain_worsening(summary, input_data, result.schedule)
            print(f"{summary.faculty_id:<10} | {summary.name:<15} | {summary.cumulative_imbalance:+.2f} | {explanation}")
        print("-" * 100)
        
    print("\nSELECTION EXPLANATION (SAMPLE LOG)")
    print("-" * 100)
    printed_count = 0
    for summary in sorted(result.faculty_summaries, key=lambda s: s.faculty_id):
        if summary.assigned_sessions:
            print(f"Faculty: {summary.name} ({summary.category_name})")
            for s_id, explanation in summary.selection_explanations.items():
                print(f"  - Session {s_id}: {explanation}")
            printed_count += 1
            if printed_count >= 5:
                print("  ... (truncated for brevity) ...")
                break
    print("=" * 100)

def main():
    STATE_FILE = "solver_state.json"
    loaded_from_state = False
    config_data = {}
    
    if os.path.exists(STATE_FILE):
        print(f"Detected existing persistence state '{STATE_FILE}'. Automatically loading configuration & history...")
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            loaded_from_state = True
        except Exception as e:
            print(f"Warning: Failed to load '{STATE_FILE}': {e}. Falling back to default loader...")

    if not loaded_from_state:
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
            print(f"Loading configuration from file: {config_path}")
            if not os.path.exists(config_path):
                print(f"Error: File '{config_path}' not found.")
                sys.exit(1)
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"Error parsing JSON file: {e}")
                sys.exit(1)
        else:
            print("No configuration file or persistence state found. Running default sample data...")
            config_data = SAMPLE_DATA
            
            sample_filename = "sample_config.json"
            try:
                with open(sample_filename, "w") as f:
                    json.dump(SAMPLE_DATA, f, indent=4)
                print(f"Created '{sample_filename}' in workspace for reference.")
            except Exception as e:
                print(f"Warning: Could not create '{sample_filename}': {e}")
                
    input_data = load_from_dict(config_data)

    day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    new_sessions = []
    print("Please specify the number of required invigilators for each shift:")
    for day in range(1, 7):
        day_name = day_names[day]
        
        # Prompt for Morning shift
        try:
            m_input = input(f"Enter number of sessions/invigilators required for Morning shift on {day_name}: ").strip()
            m_req = int(m_input) if m_input else 2
        except (KeyboardInterrupt, EOFError, ValueError):
            m_req = 2
            
        # Prompt for Afternoon shift
        try:
            a_input = input(f"Enter number of sessions/invigilators required for Afternoon shift on {day_name}: ").strip()
            a_req = int(a_input) if a_input else 2
        except (KeyboardInterrupt, EOFError, ValueError):
            a_req = 2
            
        default_duration = 2.0 if input_data.exam_type == ExamType.MIDSEM else 3.0
        day_weight = 1.5 if day == 6 else 1.0
        
        m_sess = Session(
            id=f"D{day}1",
            day=day,
            session_num=1,
            label=f"{day_name} Morning",
            required_invigilators=m_req,
            day_weight=day_weight,
            duration_hours=default_duration,
            start_time=input_data.morning_start_time
        )
        
        a_sess = Session(
            id=f"D{day}2",
            day=day,
            session_num=2,
            label=f"{day_name} Afternoon",
            required_invigilators=a_req,
            day_weight=day_weight,
            duration_hours=default_duration,
            start_time=input_data.afternoon_start_time
        )
        
        new_sessions.append(m_sess)
        new_sessions.append(a_sess)
        
    input_data.sessions = new_sessions

    ratio_mode = config_data.get("category_ratio_mode", "target_load_scaling")
    solver = InvigilationSolver(input_data, ratio_mode=ratio_mode)
    
    start_time = time.time()
    result = solver.solve()
    end_time = time.time()
    
    print_report(result, input_data)
    print(f"Solved in {((end_time - start_time) * 1000):.2f} ms")
    
    if result.success:
        updated_history = []
        for summary in result.faculty_summaries:
            updated_history.append({
                "faculty_id": summary.faculty_id,
                "previous_imbalance": summary.cumulative_imbalance
            })
            
        state_data = {
            "exam_type": input_data.exam_type.value,
            "category_ratio_mode": input_data.category_ratio_mode,
            "categories": [
                {"name": cat.name, "ratio_weight": cat.ratio_weight}
                for cat in input_data.categories.values()
            ],
            "faculty_list": [
                {
                    "id": fac.id,
                    "name": fac.name,
                    "category": fac.category_name,
                    "pg_timetable_blocks": fac.pg_timetable_blocks,
                    "availability_overrides": fac.availability_overrides
                }
                for fac in input_data.faculty_list
            ],
            "sessions": [
                {
                    "id": s.id,
                    "day": s.day,
                    "session_num": s.session_num,
                    "label": s.label,
                    "required_invigilators": s.required_invigilators,
                    "day_weight": s.day_weight,
                    "duration_hours": s.duration_hours
                }
                for s in input_data.sessions
            ],
            "history": updated_history
        }
        
        try:
            save_state_transactional(STATE_FILE, state_data)
            print(f"Successfully saved updated solver state transactionally to '{STATE_FILE}'.")
        except Exception as e:
            print(f"Error: Failed to persist solver state to '{STATE_FILE}': {e}")

if __name__ == "__main__":
    main()
