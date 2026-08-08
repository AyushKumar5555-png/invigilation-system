# Backend Code Workflow & Optimization Mechanics

This document provides a detailed technical walkthrough of the backend execution flow, including server startup bootstrapping, REST API endpoint lifecycles, and the core algorithmic solver pipeline.

---

## 1. High-Level Server Initialization Flow

When `python server.py` runs, it executes the state bootstrap procedure before listening to incoming API requests:

```mermaid
graph TD
    Start([Execute python server.py]) --> CheckState{solver_state.json exists?}
    
    CheckState -->|Yes| LoadJSON[Read configuration data from solver_state.json]
    LoadJSON --> SyncConfig[Sync state to sample_config.json]
    
    CheckState -->|No| CheckExcel{Excel roster exists?}
    CheckExcel -->|No| EmptyState[Start with empty configuration structure]
    
    CheckExcel -->|Yes| ParseExcel[Parse Seniority Wise List sheet via Pandas]
    ParseExcel --> ExtrCols[Map Employee Code to id, Name to name, Designation to category]
    ExtrCols --> CreateState[Build initial states: previous_imbalance = 0.0]
    CreateState --> SaveJSON[Write new solver_state.json & sample_config.json]
    
    SyncConfig --> StartServer[Initialize socketserver on Port 8080]
    SaveJSON --> StartServer
    EmptyState --> StartServer
    
    StartServer --> Listen[Listen for Frontend HTTP Requests]
```

---

## 2. API Endpoint Lifecycle & Requests Flow

The server processes incoming REST APIs using three primary routes:

```mermaid
sequenceDiagram
    autonumber
    actor Browser as Frontend (app.js)
    participant Server as HTTP Handler (server.py)
    participant Loader as Config Loader (config.py)
    participant Engine as Solver Engine (invigilation_scheduler.py)
    
    %% GET API/CONFIG
    Browser->>Server: GET /api/config
    Note over Server: Reads local sample_config.json
    Server-->>Browser: JSON payload (exam_type, categories, sessions, faculty_list)
    
    %% POST API/CONFIG
    Browser->>Server: POST /api/config (JSON payload)
    Note over Server: Validates JSON format
    Server->>Server: Write to sample_config.json & solver_state.json
    Server-->>Browser: HTTP 200 {"success": true}
    
    %% POST API/SOLVE
    Browser->>Server: POST /api/solve (JSON payload)
    Server->>Loader: load_from_dict(payload)
    Note over Loader: Instantiates models (Faculty, Session, History)
    Loader-->>Server: AllocationInput Dataclass Object
    Server->>Engine: InvigilationSolver(input_data)
    Note over Engine: Performs greedy allocation & local hill-climbing search
    Engine-->>Server: AllocationResult Dataclass Object
    Server->>Server: Serialize to dictionary (asdict)
    Server-->>Browser: JSON payload (success, schedule, summaries, fairness_index)
```

---

## 3. The Invigilation Solver Algorithmic Pipeline

Inside `invigilation_scheduler.py`, the core optimization algorithm operates in four distinct execution phases:

```mermaid
graph TD
    Start[1. Receive AllocationInput] --> TargetCalc[2. Calculate Target Workloads]
    
    subgraph Target Workload Calculations
        TargetCalc --> SumHours[Sum total required invigilator-hours]
        SumHours --> ScaleCat[Scale targets proportionally based on Category Ratio Weights]
        ScaleCat --> AddHistory[Factor in previous workload imbalance from history]
    end
    
    AddHistory --> GreedyInit[3. Construct Initial Schedule Greedy Heuristics]
    
    subgraph Initial Schedule Construction
        GreedyInit --> SortSess[Sort exam sessions chronologically]
        SortSess --> SelectFac[For each session slot, select faculty with lowest current hours]
        SelectFac --> VerifyHard[Check hard constraints: Max 1 duty/day, no availability overrides, no PG blocks]
    end
    
    VerifyHard --> Optimization[4. Local Search & Fairness Optimization]
    
    subgraph Local Search Optimization
        Optimization --> CalcMetrics[Calculate Jain's Index & Gini Coefficient]
        CalcMetrics --> SwapDuties[Iteratively swap duties between faculty members]
        SwapDuties --> Evaluate{Did swap improve fairness or resolve a conflict?}
        Evaluate -->|Yes| ApplySwap[Apply swap and recalculate metrics]
        Evaluate -->|No| RevertSwap[Revert swap and try next pair]
    end
    
    ApplySwap --> BuildReport[5. Compile Results]
    RevertSwap --> BuildReport
    
    subgraph Result Compilation
        BuildReport --> Diagnostic[Build conflict/feasibility reports]
        Diagnostic --> Serial[Generate AllocationResult dataclass]
    end
    
    Serial --> End([Return results to server API response])
```
