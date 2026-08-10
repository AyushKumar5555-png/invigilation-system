import json
import os
import sys

# Ensure we can import invigilation_scheduler
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from invigilation_scheduler import load_from_dict, InvigilationSolver

def check_gaps():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    input_data = load_from_dict(config)
    solver = InvigilationSolver(input_data)
    result = solver.solve()
    
    print(f"Solve success: {result.success}")
    print(f"Feasibility report: {result.feasibility_report}")
    print(f"Conflict report: {result.conflict_report}")
    
    # Map session ID to session object
    sess_map = {s.id: s for s in solver.sessions}
    
    # For every faculty member, check consecutive day duties
    violations = 0
    checked_pairs = 0
    
    # We will gather duties by day for each faculty
    for summary in result.faculty_summaries:
        f_id = summary.faculty_id
        # Find which sessions this faculty is assigned to
        assigned_sessions = []
        for sess_alloc in result.schedule:
            if f_id in sess_alloc.assigned_faculty_ids:
                assigned_sessions.append(sess_map[sess_alloc.session_id])
                
        # Group by day
        duties_by_day = {}
        for s in assigned_sessions:
            duties_by_day.setdefault(s.day, []).append(s)
            
        # Check consecutive days (physical gap in minutes)
        for day in sorted(duties_by_day.keys()):
            if day + 1 in duties_by_day:
                # We have a duty on day and day + 1
                for s1 in duties_by_day[day]:
                    for s2 in duties_by_day[day + 1]:
                        # Physical gap including day multiplier
                        gap = (s2.day * 1440 + s2.start_time) - (s1.day * 1440 + s1.start_time)
                        checked_pairs += 1
                        print(f"Faculty {summary.name} ({f_id}): Day {day} ({s1.label}, start={s1.start_time}) & Day {day+1} ({s2.label}, start={s2.start_time}) -> Gap: {gap} mins")
                        if gap < 120:
                            print(f"  [VIOLATION] Gap is {gap} minutes, which is under 120 minutes!")
                            violations += 1
                            
    print("=" * 60)
    print(f"Total checked consecutive-day pairs: {checked_pairs}")
    print(f"Total consecutive-day violations: {violations}")

if __name__ == '__main__':
    check_gaps()
