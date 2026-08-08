import json
import os
import sys

# Ensure we can import invigilation_scheduler
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from invigilation_scheduler import load_from_dict, InvigilationSolver

def run_test():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    input_data = load_from_dict(config)
    solver = InvigilationSolver(input_data)
    result = solver.solve()
    
    # Let's inspect the state of solver before it failed at D22
    # We can run the initialization and see how many eligible faculty there are for D22 (Tuesday AN)
    print("Sessions list:")
    for s in solver.sessions:
        print(f"Session {s.id} (Day {s.day}, Num {s.session_num}): start_time={s.start_time}, duration={s.duration_hours}")
        
    print("\nFaculty duties after solve:")
    # Print faculty assigned to D22
    d22_assigned = [sa.assigned_faculty_ids for sa in result.schedule if sa.session_id == 'D22'][0]
    print(f"D22 assigned ({len(d22_assigned)} / 30): {d22_assigned}")
    
    # Why were others not assigned to D22?
    print("\nInspecting non-assigned faculty eligibility for D22:")
    for f in input_data.faculty_list:
        if f.id in d22_assigned:
            continue
        # Check constraints
        day_limit = solver.faculty_duties[f.id].get(2, [])
        over_2 = len(day_limit) >= 2
        pg_block = 'D22' in f.pg_timetable_blocks
        av_override = 'D22' in f.availability_overrides
        
        # gap checks
        gap_today = False
        if 2 in solver.faculty_duties[f.id]:
            for t in solver.faculty_duties[f.id][2]:
                if abs(780 - t) < 120:
                    gap_today = True
                    
        gap_prev = False
        if 1 in solver.faculty_duties[f.id]:
            prev_times = solver.faculty_duties[f.id][1]
            if prev_times and abs(780 - max(prev_times)) < 120:
                gap_prev = True
                
        gap_next = False
        if 3 in solver.faculty_duties[f.id]:
            next_times = solver.faculty_duties[f.id][3]
            if next_times and abs(780 - min(next_times)) < 120:
                gap_next = True
                
        print(f"Faculty {f.id}: duties_today={day_limit}, over_2={over_2}, pg_block={pg_block}, av_override={av_override}, gap_today={gap_today}, gap_prev={gap_prev}, gap_next={gap_next}")

if __name__ == '__main__':
    run_test()
