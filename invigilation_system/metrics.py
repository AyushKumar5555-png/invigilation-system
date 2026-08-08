from typing import List, Dict, Optional
from .models import Faculty, FacultyCategory, Session

def calculate_session_weighted_hours(session: Session) -> float:
    """Computes the weighted hours required for a single slot in a session."""
    return session.duration_hours * session.day_weight

def calculate_total_required_weighted_hours(sessions: List[Session]) -> float:
    """Computes the sum of weighted hours required across all sessions and slots."""
    total = 0.0
    for s in sessions:
        total += s.required_invigilators * calculate_session_weighted_hours(s)
    return total

def calculate_target_loads(
    faculty_list: List[Faculty],
    categories: Dict[str, FacultyCategory],
    sessions: List[Session],
    scale_to_required: bool = True,
    custom_raw_targets: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Computes the target weighted workload (in hours) for each faculty member.
    
    If scale_to_required is True:
        The target load is scaled so that the sum of target loads equals the total required weighted hours.
    elif custom_raw_targets is provided:
        Target load is looked up from custom_raw_targets based on faculty category.
    else:
        Target load is the raw ratio_weight of the category.
    """
    if not faculty_list:
        return {}

    # Check for category validation
    for f in faculty_list:
        if f.category_name not in categories:
            raise ValueError(f"Category '{f.category_name}' for faculty '{f.id}' not found in categories dict.")

    if scale_to_required:
        total_required = calculate_total_required_weighted_hours(sessions)
        sum_weights = sum(categories[f.category_name].ratio_weight for f in faculty_list)
        
        if sum_weights == 0:
            return {f.id: 0.0 for f in faculty_list}
            
        scaling_factor = total_required / sum_weights
        return {f.id: categories[f.category_name].ratio_weight * scaling_factor for f in faculty_list}
        
    elif custom_raw_targets is not None:
        targets = {}
        for f in faculty_list:
            targets[f.id] = custom_raw_targets.get(f.category_name, categories[f.category_name].ratio_weight)
        return targets
        
    else:
        return {f.id: categories[f.category_name].ratio_weight for f in faculty_list}

def calculate_jains_index(loads: List[float]) -> float:
    """
    Computes Jain's Fairness Index for the given workloads.
    J = (sum(x_i))^2 / (n * sum(x_i^2))
    Interpretation: J = 1 is perfectly fair/equal.
    """
    n = len(loads)
    if n == 0:
        return 1.0
    
    sum_loads = sum(loads)
    if sum_loads == 0:
        # If everyone has 0 load, it is perfectly equal
        return 1.0
        
    sum_sq_loads = sum(x ** 2 for x in loads)
    return (sum_loads ** 2) / (n * sum_sq_loads)

def calculate_gini_coefficient(loads: List[float]) -> float:
    """
    Computes the Gini Coefficient for the given workloads.
    G = sum_{i,j} |x_i - x_j| / (2 * n * sum(x_i))
    Interpretation: 0 = perfect equality, 1 = perfect inequality.
    """
    n = len(loads)
    if n == 0:
        return 0.0
        
    sum_loads = sum(loads)
    if sum_loads == 0:
        return 0.0
        
    diff_sum = 0.0
    for x_i in loads:
        for x_j in loads:
            diff_sum += abs(x_i - x_j)
            
    return diff_sum / (2 * n * sum_loads)
