import sys
import json
import os
import time
from typing import Dict, Any
from invigilation_scheduler import load_from_dict, load_from_json, InvigilationSolver

SAMPLE_DATA = {
    "exam_type": "midsem",
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
        {"id": "D32", "day": 3, "session_num": 2, "label": "Wednesday AN", "required_invigilators": 4},
        {"id": "D41", "day": 4, "session_num": 1, "label": "Thursday FN", "required_invigilators": 3},
        {"id": "D42", "day": 4, "session_num": 2, "label": "Thursday AN", "required_invigilators": 2},
        {"id": "D51", "day": 5, "session_num": 1, "label": "Friday FN", "required_invigilators": 2},
        {"id": "D52", "day": 5, "session_num": 2, "label": "Friday AN", "required_invigilators": 2},
        {"id": "D61", "day": 6, "session_num": 1, "label": "Saturday FN", "required_invigilators": 2, "day_weight": 1.5},
        {"id": "D62", "day": 6, "session_num": 2, "label": "Saturday AN", "required_invigilators": 1, "day_weight": 1.5}
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

def print_result(result, input_data):
    print("=" * 100)
    print("                      UNIVERSITY INVIGILATION DUTY ALLOCATION REPORT")
    print("=" * 100)
    print(f"Feasibility Status:  {result.feasibility_report}")
    print(f"Jain's Fairness Index: {result.jains_fairness_index:.4f} (1.0 is perfectly equal/fair)")
    print(f"Gini Coefficient:      {result.gini_coefficient:.4f} (0.0 is perfect equality)")
    print("-" * 100)
    
    if not result.success:
        print("\n[!] Scheduling failed to generate a valid allocation.")
        print("Conflict / Diagnostics report:")
        for line in result.conflict_report:
            print(f"  - {line}")
        print("=" * 100)
        return

    # Print Day-wise Allocation Table
    print("\nDAY-WISE ALLOCATION SCHEDULE")
    print("-" * 100)
    header = f"{'Session':<10} | {'Day':<4} | {'Label':<15} | {'Req':<4} | {'Assigned Faculty'}"
    print(header)
    print("-" * 100)
    
    # Map session ID to list of assigned faculty names
    id_to_fac_name = {f.id: f.name for f in input_data.faculty_list}
    
    for sess_alloc in result.schedule:
        sess = next(s for s in input_data.sessions if s.id == sess_alloc.session_id)
        fac_names = [id_to_fac_name[f_id] for f_id in sess_alloc.assigned_faculty_ids]
        fac_str = ", ".join(fac_names)
        print(f"{sess.id:<10} | Day {sess.day:<2} | {sess.label:<15} | {sess.required_invigilators:<4} | {fac_str}")
    print("-" * 100)
    
    # Print Faculty-wise Workload Summary Table
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
    
    # Print explanations for selection (sample)
    print("\nSELECTION EXPLANATION (SAMPLE LOG)")
    print("-" * 100)
    printed_count = 0
    for summary in sorted(result.faculty_summaries, key=lambda s: s.faculty_id):
        if summary.assigned_sessions:
            print(f"Faculty: {summary.name} ({summary.category_name})")
            for s_id, explanation in summary.selection_explanations.items():
                print(f"  - Session {s_id}: {explanation}")
            printed_count += 1
            if printed_count >= 5:  # Limit output log
                print("  ... (truncated for brevity) ...")
                break
    print("=" * 100)

def main():
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
        # Revert to PDF sample and write out configuration file for developer reference
        print("No configuration file provided. Running default sample data (PDF Example)...")
        config_data = SAMPLE_DATA
        
        sample_filename = "sample_config.json"
        try:
            with open(sample_filename, "w") as f:
                json.dump(SAMPLE_DATA, f, indent=4)
            print(f"Created '{sample_filename}' in workspace for reference.")
        except Exception as e:
            print(f"Warning: Could not create '{sample_filename}': {e}")
            
    input_data = load_from_dict(config_data)
    
    solver = InvigilationSolver(input_data, ratio_mode="target_load_scaling")
    
    start_time = time.time()
    result = solver.solve()
    end_time = time.time()
    
    print_result(result, input_data)
    print(f"Solved in {((end_time - start_time) * 1000):.2f} ms")

if __name__ == "__main__":
    main()
