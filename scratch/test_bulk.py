import json
import os
import sys

# Ensure we can import invigilation_scheduler
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from invigilation_scheduler import load_from_dict, InvigilationSolver

def test():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_config.json')
    if not os.path.exists(config_path):
        print("Config path not found!")
        return
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    # Apply Morning=32, Afternoon=30
    morning_count = 32
    afternoon_count = 30
    for s in config['sessions']:
        if s['session_num'] == 1:
            s['required_invigilators'] = morning_count
        elif s['session_num'] == 2:
            s['required_invigilators'] = afternoon_count
            
    input_data = load_from_dict(config)
    solver = InvigilationSolver(input_data, ratio_mode=config.get("category_ratio_mode", "target_load_scaling"))
    result = solver.solve()
    
    print(f"Solver Success: {result.success}")
    print(f"Feasibility Report: {result.feasibility_report}")
    print(f"Conflicts:")
    for c in result.conflict_report:
        print(f" - {c}")
        
    print("Checking allocation results:")
    for sched in result.schedule:
        sess = next(s for s in input_data.sessions if s.id == sched.session_id)
        print(f"Session {sess.id} (Day {sess.day}, Num {sess.session_num}): Required={sess.required_invigilators}, Assigned={len(sched.assigned_faculty_ids)}")

if __name__ == '__main__':
    test()
