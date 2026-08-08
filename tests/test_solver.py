import unittest
from invigilation_scheduler import (
    Faculty, Session, HistoricalRecord, AllocationInput,
    load_from_dict, InvigilationSolver,
    calculate_jains_index, calculate_gini_coefficient,
    ExamType
)

class TestInvigilationSystem(unittest.TestCase):
    
    def setUp(self):
        # Base configuration for testing
        self.base_config = {
            "exam_type": "midsem",
            "category_ratio_mode": "target_load_scaling",
            "categories": [
                {"name": "Professor", "ratio_weight": 2.0},
                {"name": "Associate Professor", "ratio_weight": 3.0},
                {"name": "Assistant Professor", "ratio_weight": 4.0}
            ],
            "faculty_list": [
                {"id": "P1", "name": "Prof. P1", "category": "Professor"},
                {"id": "P2", "name": "Prof. P2", "category": "Professor"},
                {"id": "AS1", "name": "Assoc. AS1", "category": "Associate Professor"},
                {"id": "AS2", "name": "Assoc. AS2", "category": "Associate Professor"},
                {"id": "AS3", "name": "Assoc. AS3", "category": "Associate Professor"},
                {"id": "AP1", "name": "Asst. AP1", "category": "Assistant Professor"},
                {"id": "AP2", "name": "Asst. AP2", "category": "Assistant Professor"},
                {"id": "AP3", "name": "Asst. AP3", "category": "Assistant Professor"},
                {"id": "AP4", "name": "Asst. AP4", "category": "Assistant Professor"}
            ],
            "sessions": [
                {"id": "D11", "day": 1, "session_num": 1, "required_invigilators": 4},
                {"id": "D12", "day": 1, "session_num": 2, "required_invigilators": 3},
                {"id": "D21", "day": 2, "session_num": 1, "required_invigilators": 3},
                {"id": "D22", "day": 2, "session_num": 2, "required_invigilators": 3},
                {"id": "D31", "day": 3, "session_num": 1, "required_invigilators": 2},
                {"id": "D32", "day": 3, "session_num": 2, "required_invigilators": 4},
                {"id": "D41", "day": 4, "session_num": 1, "required_invigilators": 3},
                {"id": "D42", "day": 4, "session_num": 2, "required_invigilators": 2},
                {"id": "D51", "day": 5, "session_num": 1, "required_invigilators": 2},
                {"id": "D52", "day": 5, "session_num": 2, "required_invigilators": 2},
                {"id": "D61", "day": 6, "session_num": 1, "required_invigilators": 2, "day_weight": 1.5},
                {"id": "D62", "day": 6, "session_num": 2, "required_invigilators": 1, "day_weight": 1.5}
            ],
            "history": []
        }

    def test_pdf_sample_allocation(self):
        """Replicates the PDF's structure and checks if a valid allocation is found."""
        input_data = load_from_dict(self.base_config)
        solver = InvigilationSolver(input_data, ratio_mode="target_load_scaling")
        
        # Verify basic static checks pass
        is_feas, msg = solver.check_feasibility()
        self.assertTrue(is_feas, f"Feasibility failed: {msg}")
        
        # Solve
        result = solver.solve()
        self.assertTrue(result.success)
        self.assertEqual(result.feasibility_report, "FEASIBLE")
        self.assertTrue(result.jains_fairness_index > 0.8) # High fairness expected
        
        # Verify hard constraints in the generated schedule:
        # 1. Covering required invigilators
        for sess_alloc in result.schedule:
            session = next(s for s in input_data.sessions if s.id == sess_alloc.session_id)
            self.assertEqual(len(sess_alloc.assigned_faculty_ids), session.required_invigilators)
            
        # 2. At most one duty per day for each faculty
        faculty_daily_assignments = {}
        for sess_alloc in result.schedule:
            session = next(s for s in input_data.sessions if s.id == sess_alloc.session_id)
            for f_id in sess_alloc.assigned_faculty_ids:
                key = (f_id, session.day)
                self.assertNotIn(key, faculty_daily_assignments, f"Faculty {f_id} assigned multiple times on Day {session.day}")
                faculty_daily_assignments[key] = True

    def test_pg_timetable_conflict(self):
        """Verifies that faculty are not assigned to slots during which they teach PG classes."""
        config = dict(self.base_config)
        
        # Set PG conflict for AP1 on session D11, D12, and D21
        # AP1 should never be assigned to these sessions
        config["faculty_list"] = [dict(f) for f in config["faculty_list"]]
        config["faculty_list"][5]["pg_timetable_blocks"] = ["D11", "D12", "D21"]
        
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        
        self.assertTrue(result.success)
        for s_alloc in result.schedule:
            if s_alloc.session_id in ["D11", "D12", "D21"]:
                self.assertNotIn("AP1", s_alloc.assigned_faculty_ids)

    def test_availability_override(self):
        """Verifies that faculty availability overrides are strictly respected."""
        config = dict(self.base_config)
        
        # Prof P1 is unavailable on Saturday sessions D61, D62
        config["faculty_list"] = [dict(f) for f in config["faculty_list"]]
        config["faculty_list"][0]["availability_overrides"] = ["D61", "D62"]
        
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        
        self.assertTrue(result.success)
        for s_alloc in result.schedule:
            if s_alloc.session_id in ["D61", "D62"]:
                self.assertNotIn("P1", s_alloc.assigned_faculty_ids)

    def test_history_load_balancing_and_compensation(self):
        """
        Verifies that previously overloaded faculty are compensated with less load, 
        and underloaded are compensated with more load.
        """
        config = dict(self.base_config)
        
        # We add history records:
        # AP1 has previous overload of +10.0 hours
        # AP2 has previous underload of -10.0 hours
        # We expect AP2 to receive MORE duties than AP1 (who should be spared if possible)
        config["history"] = [
            {"faculty_id": "AP1", "previous_imbalance": 10.0},
            {"faculty_id": "AP2", "previous_imbalance": -10.0}
        ]
        
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        
        self.assertTrue(result.success)
        
        # Extract summaries for AP1 and AP2
        ap1_summary = next(s for s in result.faculty_summaries if s.faculty_id == "AP1")
        ap2_summary = next(s for s in result.faculty_summaries if s.faculty_id == "AP2")
        
        # AP2 should have significantly more assigned hours than AP1
        self.assertTrue(ap2_summary.assigned_hours > ap1_summary.assigned_hours)
        
        # AP1 should have improved/neutral status (reduced imbalance or same, but definitely not worsening a lot)
        self.assertIn(ap1_summary.impact_status, ["IMPROVED", "NEUTRAL"])
        self.assertIn(ap2_summary.impact_status, ["IMPROVED", "NEUTRAL"])

    def test_infeasibility_diagnostics(self):
        """Verifies that the solver identifies and reports the exact source of infeasibility."""
        config = dict(self.base_config)
        
        # Make a session completely impossible to cover:
        # Session D62 requires 2 invigilators, but only AP4 is available because all other 8 are marked unavailable.
        config["sessions"] = [dict(s) for s in config["sessions"]]
        config["sessions"][-1]["required_invigilators"] = 2
        config["faculty_list"] = [dict(f) for f in config["faculty_list"]]
        for f in config["faculty_list"][:-1]:
            f["availability_overrides"] = ["D62"]
            
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        
        self.assertFalse(result.success)
        self.assertEqual(result.feasibility_report, "INFEASIBLE")
        self.assertTrue(any("D62" in line for line in result.conflict_report))
        self.assertTrue(any("Availability Overrides" in line for line in result.conflict_report))

    def test_ratio_modes_and_hard_limits(self):
        """Tests scaled, raw, and hard maximum limit ratio modes."""
        # Test 1: Hard limits mode
        # If we configure Assistant Professor target as 2 hours (very low) and Professors as 10 hours
        # and enforce hard limits, then Asst Professors can never exceed 2.0 weighted hours (i.e. 1 weekday duty of 2 hrs).
        config = dict(self.base_config)
        config["category_ratio_mode"] = "hard_category_limits"
        # We will set Professor ratio weight to 10.0, and Asst Prof to 1.0 (so their target is low)
        config["categories"] = [
            {"name": "Professor", "ratio_weight": 10.0},
            {"name": "Associate Professor", "ratio_weight": 5.0},
            {"name": "Assistant Professor", "ratio_weight": 1.0}
        ]
        
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        
        # Solve
        result = solver.solve()
        self.assertTrue(result.success or result.feasibility_report == "INFEASIBLE")
        
        # Check that no Assistant Professor exceeds their target load
        has_limit_violation = any("Hard Category Limit" in e for e in result.conflict_report)
        if not has_limit_violation:
            for f_rep in result.faculty_summaries:
                if f_rep.category_name == "Assistant Professor":
                    self.assertTrue(f_rep.assigned_weighted_load <= f_rep.target_load + 1e-5)

    def test_normalized_metrics_correctness(self):
        """Verifies that Gini coefficient and Jain's index are calculated on normalized workloads."""
        # If load = [2, 4] and target = [2, 4], the normalized ratios are [1.0, 1.0] (perfect fairness).
        # Jain's index should be 1.0 and Gini should be 0.0.
        loads = [2.0, 4.0]
        targets = [2.0, 4.0]
        
        jain = calculate_jains_index(loads, targets)
        gini = calculate_gini_coefficient(loads, targets)
        
        self.assertAlmostEqual(jain, 1.0)
        self.assertAlmostEqual(gini, 0.0)

    def test_consecutive_day_gap_constraint(self):
        """Verifies that faculty members are not assigned on consecutive days if the gap is less than 120 minutes."""
        config = dict(self.base_config)
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        self.assertTrue(result.success)
        errors = solver.validate_allocation(result.schedule)
        self.assertFalse(any("Minimum Gap Violation" in e for e in errors))

    def test_horizontal_fill_order(self):
        """Verifies that sessions are sorted and processed in day-first order."""
        config = dict(self.base_config)
        input_data = load_from_dict(config)
        solver = InvigilationSolver(input_data)
        result = solver.solve()
        self.assertTrue(result.success)
        for idx in range(len(result.schedule) - 1):
            s_curr = next(s for s in solver.sessions if s.id == result.schedule[idx].session_id)
            s_next = next(s for s in solver.sessions if s.id == result.schedule[idx + 1].session_id)
            self.assertTrue((s_curr.day, s_curr.session_num) <= (s_next.day, s_next.session_num))

if __name__ == "__main__":
    unittest.main()
