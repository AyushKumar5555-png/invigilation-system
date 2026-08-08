import time
import random
from typing import List, Dict, Set, Tuple, Optional
from .models import (
    Faculty, Session, HistoricalRecord, AllocationInput, 
    AllocationResult, SessionAllocation, FacultyReport, ExamType
)
from .metrics import (
    calculate_target_loads, calculate_jains_index, 
    calculate_gini_coefficient, calculate_session_weighted_hours
)

class InvigilationSolver:
    def __init__(self, input_data: AllocationInput, scale_targets: bool = True, custom_raw_targets: Optional[Dict[str, float]] = None):
        self.input_data = input_data
        self.scale_targets = scale_targets
        self.custom_raw_targets = custom_raw_targets
        
        # Build category map and faculty map
        self.categories = input_data.categories
        self.faculty_map = {f.id: f for f in input_data.faculty_list}
        self.faculty_index = {f.id: i for i, f in enumerate(input_data.faculty_list)}
        self.sessions = sorted(input_data.sessions, key=lambda s: s.id)
        
        # Build history map
        self.history_map = {f.id: 0.0 for f in input_data.faculty_list}
        for record in input_data.history:
            if record.faculty_id in self.history_map:
                self.history_map[record.faculty_id] = record.previous_imbalance
                
        # Calculate target loads
        self.target_loads = calculate_target_loads(
            faculty_list=input_data.faculty_list,
            categories=self.categories,
            sessions=self.sessions,
            scale_to_required=self.scale_targets,
            custom_raw_targets=self.custom_raw_targets
        )
        
    def validate_allocation(self, schedule: List[SessionAllocation]) -> List[str]:
        """
        Explicitly validates the generated schedule against all hard constraints.
        Returns a list of validation error messages. If empty, the schedule is fully valid.
        """
        errors = []
        # 1. Check session coverage
        assigned_slots = {sa.session_id: sa.assigned_faculty_ids for sa in schedule}
        for session in self.sessions:
            assigned_facs = assigned_slots.get(session.id, [])
            if len(assigned_facs) != session.required_invigilators:
                errors.append(
                    f"Session Coverage Violation: Session {session.id} ({session.label}) requires "
                    f"{session.required_invigilators} invigilators, but has {len(assigned_facs)} assigned."
                )
                
        # 2. Check at-most-one duty per day and conflicts
        # Group duties by faculty and day
        faculty_day_duties: Dict[str, Dict[int, List[str]]] = {}
        for sa in schedule:
            session = next((s for s in self.sessions if s.id == sa.session_id), None)
            if not session:
                continue
            for f_id in sa.assigned_faculty_ids:
                faculty_day_duties.setdefault(f_id, {}).setdefault(session.day, []).append(session.id)
                
                # Check PG conflicts (only for midsem)
                if self.input_data.exam_type == ExamType.MIDSEM:
                    faculty = self.faculty_map[f_id]
                    if session.id in faculty.pg_timetable_blocks:
                        errors.append(
                            f"PG Timetable Conflict: Faculty {faculty.name} ({f_id}) is assigned to "
                            f"Session {session.id} ({session.label}) despite having a PG lecture block."
                        )
                        
                # Check availability overrides
                faculty = self.faculty_map[f_id]
                if session.id in faculty.availability_overrides:
                    errors.append(
                        f"Availability Violation: Faculty {faculty.name} ({f_id}) is assigned to "
                        f"Session {session.id} ({session.label}) despite being marked unavailable."
                    )
                    
        # Check daily limits (at most one duty per day)
        for f_id, day_map in faculty_day_duties.items():
            faculty = self.faculty_map[f_id]
            for day, sessions in day_map.items():
                if len(sessions) > 1:
                    errors.append(
                        f"One Duty Per Day Violation: Faculty {faculty.name} ({f_id}) is assigned to "
                        f"multiple sessions ({', '.join(sessions)}) on Day {day}."
                    )
                    
        return errors

    def check_feasibility(self) -> Tuple[bool, str]:
        """
        Performs static checks to determine if the scheduling problem is feasible.
        Returns (is_feasible, diagnostic_message).
        """
        if not self.input_data.faculty_list:
            return False, "Feasibility Check Failed: No faculty members provided in the input."
        if not self.sessions:
            return False, "Feasibility Check Failed: No exam sessions provided in the input."
            
        # 1. Check if each session has enough available faculty (PG conflicts & Availability overrides)
        for session in self.sessions:
            available_faculty = self._get_available_faculty_for_session(session, ignore_pg=False, ignore_overrides=False)
            if len(available_faculty) < session.required_invigilators:
                return False, (
                    f"Feasibility Check Failed: Session {session.id} ({session.label}) requires "
                    f"{session.required_invigilators} invigilators, but only {len(available_faculty)} "
                    f"faculty members are available due to PG class conflicts or availability overrides."
                )
                
        # 2. Check daily unique faculty capacity (since a faculty can only do at most 1 duty per day)
        day_sessions: Dict[int, List[Session]] = {}
        for session in self.sessions:
            day_sessions.setdefault(session.day, []).append(session)
            
        for day, sessions_on_day in day_sessions.items():
            day_req = sum(s.required_invigilators for s in sessions_on_day)
            available_on_day: Set[str] = set()
            for session in sessions_on_day:
                available_on_day.update(
                    f.id for f in self._get_available_faculty_for_session(session, ignore_pg=False, ignore_overrides=False)
                )
            if len(available_on_day) < day_req:
                session_labels = ", ".join(s.id for s in sessions_on_day)
                return False, (
                    f"Feasibility Check Failed: Day {day} (sessions: {session_labels}) requires a total "
                    f"of {day_req} invigilators, but only {len(available_on_day)} unique faculty members "
                    f"are available on this day (respecting PG classes and overrides). Each faculty can do at most 1 duty/day."
                )
                
        return True, "Passed basic static feasibility checks."

    def _get_available_faculty_for_session(self, session: Session, ignore_pg: bool = False, ignore_overrides: bool = False) -> List[Faculty]:
        """Returns the list of faculty members who do not have PG/availability conflicts for the session."""
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
        """
        Runs diagnostic evaluations to identify which constraints cause infeasibility by relaxing them.
        """
        temp_solver_no_pg = InvigilationSolver(self.input_data, self.scale_targets, self.custom_raw_targets)
        for f in temp_solver_no_pg.input_data.faculty_list:
            f.pg_timetable_blocks = []
        is_feas, msg = temp_solver_no_pg.check_feasibility()
        if is_feas:
            res = temp_solver_no_pg.solve(max_steps=5000)
            if res.success:
                return (
                    "Infeasibility Cause: PG Timetable Conflicts. "
                    "The schedule becomes feasible if faculty lecture schedules are suspended or ignored."
                )

        temp_solver_no_override = InvigilationSolver(self.input_data, self.scale_targets, self.custom_raw_targets)
        for f in temp_solver_no_override.input_data.faculty_list:
            f.availability_overrides = []
        is_feas, msg = temp_solver_no_override.check_feasibility()
        if is_feas:
            res = temp_solver_no_override.solve(max_steps=5000)
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
                    f.id for f in self._get_available_faculty_for_session(session, ignore_pg=False, ignore_overrides=False)
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

    def _get_objective(self, assign_dict: Dict[str, List[str]], load_dict: Dict[str, float]) -> float:
        """
        Calculates the objective function to minimize.
        Formulation: sum( (H_f + A_f - T_f)^2 ) + unfilled_slots * 10000.0
        """
        obj = 0.0
        for f_id in self.target_loads:
            diff = self.history_map[f_id] + load_dict[f_id] - self.target_loads[f_id]
            obj += diff ** 2
        
        # Unassigned slot penalty (heavily prioritizes filling slots)
        unassigned_count = 0
        for session in self.sessions:
            assigned_count = len(assign_dict.get(session.id, []))
            missing = session.required_invigilators - assigned_count
            unassigned_count += missing
            
        obj += unassigned_count * 10000.0
        return obj

    def _run_greedy_initialization(self) -> Tuple[float, Dict[str, List[str]]]:
        """
        Runs a quick greedy heuristic to construct a valid initial solution.
        This provides a starting point for local search and backtracking.
        """
        assignment = {}
        faculty_daily_duties = {f.id: set() for f in self.input_data.faculty_list}
        faculty_weighted_load = {f.id: 0.0 for f in self.input_data.faculty_list}
        
        # Sort sessions: saturday sessions and sessions with fewer available faculty first
        session_avail_counts = []
        for s in self.sessions:
            avail = self._get_available_faculty_for_session(s)
            session_avail_counts.append((s, len(avail)))
        sorted_sessions = [
            x[0] for x in sorted(
                session_avail_counts, 
                key=lambda x: (x[1], -x[0].day_weight, x[0].id)
            )
        ]
        
        for session in sorted_sessions:
            available = self._get_available_faculty_for_session(session)
            eligible = [f for f in available if session.day not in faculty_daily_duties[f.id]]
            
            # Sort eligible faculty by: current load + history - target
            eligible.sort(key=lambda f: self.history_map[f.id] + faculty_weighted_load[f.id] - self.target_loads[f.id])
            
            # Assign as many as possible up to required_invigilators (could be less if supply is low)
            selected = eligible[:session.required_invigilators]
            assignment[session.id] = [f.id for f in selected]
            
            w_hrs = calculate_session_weighted_hours(session)
            for f in selected:
                faculty_daily_duties[f.id].add(session.day)
                faculty_weighted_load[f.id] += w_hrs
                
        obj = self._get_objective(assignment, faculty_weighted_load)
        return obj, assignment

    def _run_local_search(self, initial_assignment: Dict[str, List[str]], max_iterations: int = 20000) -> Tuple[float, Dict[str, List[str]]]:
        """
        Refines the initial assignment using Hill Climbing.
        """
        random.seed(42)
        
        assignment = {s_id: list(facs) for s_id, facs in initial_assignment.items()}
        faculty_daily_duties = {f.id: set() for f in self.input_data.faculty_list}
        faculty_weighted_load = {f.id: 0.0 for f in self.input_data.faculty_list}
        
        for s_id, facs in assignment.items():
            session = next(s for s in self.sessions if s.id == s_id)
            w_hrs = calculate_session_weighted_hours(session)
            for f_id in facs:
                faculty_daily_duties[f_id].add(session.day)
                faculty_weighted_load[f_id] += w_hrs
                
        current_obj = self._get_objective(assignment, faculty_weighted_load)
        best_obj = current_obj
        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
        
        for _ in range(max_iterations):
            move_type = random.choice(["swap_faculty", "swap_sessions", "fill_unassigned"])
            
            if move_type == "swap_faculty":
                # Move 1: Swap an assigned faculty in a session with an available unassigned faculty
                session = random.choice(self.sessions)
                assigned_facs = assignment[session.id]
                if not assigned_facs:
                    continue
                    
                f1_id = random.choice(assigned_facs)
                f2 = random.choice(self.input_data.faculty_list)
                f2_id = f2.id
                
                if f1_id == f2_id:
                    continue
                    
                if session.day in faculty_daily_duties[f2_id]:
                    continue
                available_for_sess = self._get_available_faculty_for_session(session)
                if f2_id not in [f.id for f in available_for_sess]:
                    continue
                    
                w_hrs = calculate_session_weighted_hours(session)
                
                # Propose swap
                faculty_weighted_load[f1_id] -= w_hrs
                faculty_daily_duties[f1_id].remove(session.day)
                faculty_weighted_load[f2_id] += w_hrs
                faculty_daily_duties[f2_id].add(session.day)
                
                new_obj = self._get_objective(assignment, faculty_weighted_load)
                
                if new_obj < current_obj:
                    assigned_facs.remove(f1_id)
                    assigned_facs.append(f2_id)
                    current_obj = new_obj
                    if current_obj < best_obj:
                        best_obj = current_obj
                        best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
                else:
                    # Revert
                    faculty_weighted_load[f1_id] += w_hrs
                    faculty_daily_duties[f1_id].add(session.day)
                    faculty_weighted_load[f2_id] -= w_hrs
                    faculty_daily_duties[f2_id].remove(session.day)
                    
            elif move_type == "swap_sessions":
                # Move 2: Swap duties between two sessions
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
                    
                # Verify compatibility
                if s2.day != s1.day:
                    if s2.day in faculty_daily_duties[f1_id]:
                        continue
                    if s1.day in faculty_daily_duties[f2_id]:
                        continue
                
                s1_avail = [f.id for f in self._get_available_faculty_for_session(s1)]
                s2_avail = [f.id for f in self._get_available_faculty_for_session(s2)]
                if f1_id not in s2_avail or f2_id not in s1_avail:
                    continue
                    
                # Propose swap
                w1 = calculate_session_weighted_hours(s1)
                w2 = calculate_session_weighted_hours(s2)
                
                faculty_weighted_load[f1_id] += w2 - w1
                faculty_weighted_load[f2_id] += w1 - w2
                
                if s1.day != s2.day:
                    faculty_daily_duties[f1_id].remove(s1.day)
                    faculty_daily_duties[f1_id].add(s2.day)
                    faculty_daily_duties[f2_id].remove(s2.day)
                    faculty_daily_duties[f2_id].add(s1.day)
                
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
                    # Revert
                    faculty_weighted_load[f1_id] -= w2 - w1
                    faculty_weighted_load[f2_id] -= w1 - w2
                    
                    if s1.day != s2.day:
                        faculty_daily_duties[f1_id].add(s1.day)
                        faculty_daily_duties[f1_id].remove(s2.day)
                        faculty_daily_duties[f2_id].add(s2.day)
                        faculty_daily_duties[f2_id].remove(s1.day)
                        
            elif move_type == "fill_unassigned":
                # Move 3: Fill an unassigned slot in a session
                session = random.choice(self.sessions)
                assigned_facs = assignment[session.id]
                if len(assigned_facs) < session.required_invigilators:
                    # Find eligible faculty who don't have duties today and are not yet assigned to this session
                    available_for_sess = self._get_available_faculty_for_session(session)
                    eligible = [
                        f.id for f in available_for_sess 
                        if session.day not in faculty_daily_duties[f.id]
                        and f.id not in assigned_facs
                    ]
                    if eligible:
                        f2_id = random.choice(eligible)
                        w_hrs = calculate_session_weighted_hours(session)
                        
                        # Assign
                        faculty_weighted_load[f2_id] += w_hrs
                        faculty_daily_duties[f2_id].add(session.day)
                        assigned_facs.append(f2_id)
                        
                        new_obj = self._get_objective(assignment, faculty_weighted_load)
                        if new_obj < current_obj:
                            current_obj = new_obj
                            if current_obj < best_obj:
                                best_obj = current_obj
                                best_assignment = {s_id: list(facs) for s_id, facs in assignment.items()}
                        else:
                            # Revert
                            faculty_weighted_load[f2_id] -= w_hrs
                            faculty_daily_duties[f2_id].remove(session.day)
                            assigned_facs.remove(f2_id)
                
        return best_obj, best_assignment

    def solve(self, max_steps: int = 100000) -> AllocationResult:
        """
        Solves the invigilation scheduling optimization problem using hybrid search.
        If a perfect allocation is impossible, it returns the best feasible partial schedule.
        """
        # 1. Greedy initialization (can return partial schedule)
        greedy_obj, greedy_assignment = self._run_greedy_initialization()
        
        best_assignment: Dict[str, List[str]] = {}
        best_obj = float('inf')
        
        if greedy_obj != float('inf'):
            # 2. Local search optimization to establish a tight bound
            best_obj, best_assignment = self._run_local_search(greedy_assignment)

        # 3. If backtracking limit is > 0, run exact search to improve local search if possible
        if max_steps > 0 and best_obj > 0.0:
            session_avail_counts = []
            for s in self.sessions:
                avail = self._get_available_faculty_for_session(s)
                session_avail_counts.append((s, len(avail)))
            
            sorted_sessions = [
                x[0] for x in sorted(
                    session_avail_counts, 
                    key=lambda x: (x[1], -x[0].day_weight, x[0].id)
                )
            ]
            
            current_assignment: Dict[str, List[str]] = {s.id: [] for s in self.sessions}
            faculty_daily_duties: Dict[str, Set[int]] = {f.id: set() for f in self.input_data.faculty_list}
            faculty_weighted_load: Dict[str, float] = {f.id: 0.0 for f in self.input_data.faculty_list}
            
            # Initialize lower bound including unassigned slots penalty
            initial_unassigned = sum(s.required_invigilators for s in self.sessions)
            initial_lb = initial_unassigned * 10000.0
            for f in self.input_data.faculty_list:
                diff = self.history_map[f.id] - self.target_loads[f.id]
                if diff > 0:
                    initial_lb += diff ** 2
                    
            partial_lb = [initial_lb]
            step_count = [0]
            timeout_reached = [False]
            
            def backtrack(session_idx: int, slot_idx: int, last_fac_idx: int):
                step_count[0] += 1
                if step_count[0] > max_steps:
                    timeout_reached[0] = True
                    return
                    
                current_session = sorted_sessions[session_idx]
                req_inv = current_session.required_invigilators
                
                if slot_idx == req_inv:
                    if session_idx + 1 == len(sorted_sessions):
                        obj = self._get_objective(current_assignment, faculty_weighted_load)
                        nonlocal best_obj, best_assignment
                        if obj < best_obj:
                            best_obj = obj
                            best_assignment = {s_id: list(facs) for s_id, facs in current_assignment.items()}
                        return
                    else:
                        backtrack(session_idx + 1, 0, -1)
                        return

                available_fac = self._get_available_faculty_for_session(current_session)
                
                eligible_fac = []
                for fac in available_fac:
                    fac_idx = self.faculty_index[fac.id]
                    if fac_idx <= last_fac_idx:
                        continue
                    if current_session.day in faculty_daily_duties[fac.id]:
                        continue
                    eligible_fac.append((fac, fac_idx))
                    
                eligible_fac.sort(key=lambda x: self.history_map[x[0].id] + faculty_weighted_load[x[0].id] - self.target_loads[x[0].id])
                
                slot_weighted_hrs = calculate_session_weighted_hours(current_session)
                
                # Option 1: Try assigning eligible faculty members
                for fac, fac_idx in eligible_fac:
                    if timeout_reached[0]:
                        break
                        
                    old_load = faculty_weighted_load[fac.id]
                    old_diff = self.history_map[fac.id] + old_load - self.target_loads[fac.id]
                    old_contrib = old_diff ** 2 if old_diff > 0 else 0.0
                    
                    # Assign
                    current_assignment[current_session.id].append(fac.id)
                    faculty_daily_duties[fac.id].add(current_session.day)
                    faculty_weighted_load[fac.id] += slot_weighted_hrs
                    
                    new_load = faculty_weighted_load[fac.id]
                    new_diff = self.history_map[fac.id] + new_load - self.target_loads[fac.id]
                    new_contrib = new_diff ** 2 if new_diff > 0 else 0.0
                    
                    diff_contrib = new_contrib - old_contrib
                    # We subtract 10000 since a slot has been filled
                    partial_lb[0] += diff_contrib - 10000.0
                    
                    if partial_lb[0] < best_obj:
                        backtrack(session_idx, slot_idx + 1, fac_idx)
                    
                    # Unassign
                    current_assignment[current_session.id].pop()
                    faculty_daily_duties[fac.id].remove(current_session.day)
                    faculty_weighted_load[fac.id] -= slot_weighted_hrs
                    partial_lb[0] -= diff_contrib - 10000.0
                    
                # Option 2: Try leaving it unassigned
                if timeout_reached[0]:
                    return
                    
                if partial_lb[0] < best_obj:
                    # Note: we do not subtract 10000 since it remains unassigned
                    backtrack(session_idx, slot_idx + 1, last_fac_idx)

            backtrack(0, 0, -1)
        
        # Build results
        schedule = [
            SessionAllocation(session_id=s_id, assigned_faculty_ids=facs)
            for s_id, facs in best_assignment.items()
        ]
        
        # Calculate final metrics and compile reports
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
                
        # Explicit validation checks
        validation_errors = self.validate_allocation(schedule)
        
        coverage_errors = [e for e in validation_errors if "Coverage" in e]
        other_errors = [e for e in validation_errors if "Coverage" not in e]
        
        success = (len(validation_errors) == 0)
        
        # Construct diagnostic explanation
        diagnostic_report = []
        if other_errors:
            feasibility_status = f"INFEASIBLE (Hard constraint violations: {', '.join(other_errors)})"
            diagnostic_report.extend(other_errors)
        elif coverage_errors:
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
                        f"Available unique faculty for this session due to PG conflicts/overrides: {', '.join(fac_names) if fac_names else 'None'}"
                    )
            feasibility_status = f"PARTIAL FEASIBLE (Unfilled sessions: {', '.join(unfilled_sessions)})"
            
            # Run relaxation diagnostics to pinpoint main source of infeasibility
            relaxation_source = self.run_diagnostics()
            diagnostic_report.append(f"Diagnostics: {relaxation_source}")
        else:
            feasibility_status = "FEASIBLE"

        # Generate explanations & impact report
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
            
            # Determine history impact
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
                    reason_parts.append(f"Assigned despite historical overload of {h_f:+.1f} hrs to meet session coverage requirements")
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
            
        loads_list = list(final_loads.values())
        jains = calculate_jains_index(loads_list)
        gini = calculate_gini_coefficient(loads_list)
        
        history_report = (
            f"History Impact Analysis: Out of {len(self.input_data.faculty_list)} faculty members, "
            f"{improved_count} improved their load balance (closer to target), "
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
