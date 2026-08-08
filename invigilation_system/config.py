import json
from typing import Dict, Any, List
from .models import (
    Faculty, FacultyCategory, Session, HistoricalRecord, 
    AllocationInput, ExamType
)

def load_from_dict(data: Dict[str, Any]) -> AllocationInput:
    """
    Parses a configuration dictionary into an AllocationInput object, 
    applying default values where necessary.
    """
    exam_type_str = data.get("exam_type", "midsem").lower()
    exam_type = ExamType.MIDSEM if exam_type_str == "midsem" else ExamType.ENDSEM
    
    # 1. Parse categories
    categories_raw = data.get("categories", {})
    categories: Dict[str, FacultyCategory] = {}
    
    # Check if categories is a list or dict
    if isinstance(categories_raw, list):
        for cat in categories_raw:
            name = cat["name"]
            weight = float(cat.get("ratio_weight", 1.0))
            categories[name] = FacultyCategory(name=name, ratio_weight=weight)
    elif isinstance(categories_raw, dict):
        for name, weight in categories_raw.items():
            # could be a simple dict like {"Professor": 2.0} or dict of dicts
            if isinstance(weight, dict):
                w_val = float(weight.get("ratio_weight", 1.0))
            else:
                w_val = float(weight)
            categories[name] = FacultyCategory(name=name, ratio_weight=w_val)
    else:
        raise ValueError("Categories must be a list or dictionary.")

    # 2. Parse faculty list
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

    # Default durations: midsem = 2.0 hrs, endsem = 3.0 hrs
    default_duration = 2.0 if exam_type == ExamType.MIDSEM else 3.0

    morning_start = int(data.get("morning_start_time", 540))
    afternoon_start = int(data.get("afternoon_start_time", 780))

    # 3. Parse sessions
    sessions_raw = data.get("sessions", [])
    sessions: List[Session] = []
    for s in sessions_raw:
        s_id = s["id"]
        day = int(s["day"])
        sess_num = int(s["session_num"])
        label = s.get("label", f"Day {day} Session {sess_num}")
        req_inv = int(s["required_invigilators"])
        
        # Default day weight: 1.5 for Saturday (day 6), 1.0 otherwise
        default_day_weight = 1.5 if day == 6 else 1.0
        day_weight = float(s.get("day_weight", default_day_weight))
        
        duration = float(s.get("duration_hours", default_duration))
        
        start_time = s.get("start_time")
        if start_time is None:
            start_time = morning_start if sess_num == 1 else afternoon_start
        else:
            start_time = int(start_time)
        
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

    # 4. Parse history
    history_raw = data.get("history", [])
    history: List[HistoricalRecord] = []
    
    # Support dict format: {"faculty_id": value} or list of dicts: [{"faculty_id": "P1", "previous_imbalance": 0.0}]
    if isinstance(history_raw, list):
        for h in history_raw:
            f_id = h["faculty_id"]
            val = float(h.get("previous_imbalance", 0.0))
            history.append(HistoricalRecord(faculty_id=f_id, previous_imbalance=val))
    elif isinstance(history_raw, dict):
        for f_id, val in history_raw.items():
            history.append(HistoricalRecord(faculty_id=f_id, previous_imbalance=float(val)))

    return AllocationInput(
        faculty_list=faculty_list,
        categories=categories,
        sessions=sessions,
        history=history,
        exam_type=exam_type,
        morning_start_time=morning_start,
        afternoon_start_time=afternoon_start
    )

def load_from_json(json_str: str) -> AllocationInput:
    """Parses a JSON string into an AllocationInput object."""
    data = json.loads(json_str)
    return load_from_dict(data)
