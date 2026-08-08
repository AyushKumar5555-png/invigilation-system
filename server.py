import http.server
import socketserver
import json
import os
import sys
from dataclasses import asdict
import pandas as pd

# Ensure we can import invigilation_scheduler
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from invigilation_scheduler import load_from_dict, InvigilationSolver

PORT = int(os.environ.get("PORT", 8080))
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

def bootstrap_state():
    state_path = os.path.join(WORKSPACE_DIR, 'solver_state.json')
    config_path = os.path.join(WORKSPACE_DIR, 'sample_config.json')
    excel_path = os.path.join(WORKSPACE_DIR, 'Faculty List (Emp. Code, Phone No. and E-mail ID).xlsx')
    
    # 1. If sample_config.json exists, load it directly and use it as-is.
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            print("Loaded state from sample_config.json")
            return config_data
        except Exception as e:
            print(f"Error loading sample_config.json: {e}")
            
    # 2. Only fall back to solver_state.json if sample_config.json does NOT exist at all.
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            # Sync to sample_config.json
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=4)
            print("Loaded state from solver_state.json (fallback)")
            return state_data
        except Exception as e:
            print(f"Error loading solver_state.json: {e}")
            
    # 3. If neither exists, parse the Excel file
    print("Neither sample_config.json nor solver_state.json found. Bootstrapping from Excel roster...")
    if not os.path.exists(excel_path):
        print(f"Excel roster not found at {excel_path}!")
        return {}
        
    try:
        df = pd.read_excel(excel_path, sheet_name='Seniority Wise List')
        new_faculties = []
        new_history = []
        
        for idx, row in df.iterrows():
            if len(row) < 5:
                continue
            emp_code = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
            name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
            designation = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
            phone_num = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''
            
            # Filter spacer/empty rows
            if not emp_code or emp_code.lower() in ['empl. code', 'nan', 'empl code']:
                continue
                
            # Standardize category to Professor, Associate Professor, Assistant Professor
            category = 'Assistant Professor'
            if 'assistant professor' in designation.lower():
                category = 'Assistant Professor'
            elif 'associate professor' in designation.lower():
                category = 'Associate Professor'
            elif 'professor' in designation.lower():
                category = 'Professor'
                
            new_faculties.append({
                "id": emp_code,
                "name": name,
                "category": category,
                "phone": phone_num,
                "pg_timetable_blocks": [],
                "availability_overrides": []
            })
            new_history.append({
                "faculty_id": emp_code,
                "previous_imbalance": 0.0
            })
            
        # Load other config structures (sessions, categories) from sample_config.json if available
        base_config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                try:
                    base_config = json.load(f)
                except Exception:
                    pass
                    
        state_data = {
            "exam_type": base_config.get("exam_type", "midsem"),
            "category_ratio_mode": base_config.get("category_ratio_mode", "target_load_scaling"),
            "categories": base_config.get("categories", [
                {"name": "Professor", "ratio_weight": 2.0},
                {"name": "Associate Professor", "ratio_weight": 3.0},
                {"name": "Assistant Professor", "ratio_weight": 4.0}
            ]),
            "faculty_list": new_faculties,
            "sessions": base_config.get("sessions", []),
            "history": new_history
        }
        
        # Save to solver_state.json
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=4)
        # Also sync to sample_config.json
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=4)
            
        print(f"Bootstrapped solver state successfully with {len(new_faculties)} faculties.")
        return state_data
    except Exception as e:
        print(f"Failed to bootstrap solver state: {e}")
        return {}

class InvigilationHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WORKSPACE_DIR, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/config':
            self.handle_get_config()
        elif self.path.startswith('/api/faculty/') and self.path.endswith('/weekly-report'):
            self.handle_get_faculty_report()
        else:
            super().do_GET()

    def handle_get_faculty_report(self):
        try:
            parts = self.path.split('/')
            faculty_id = parts[3]
            config_path = os.path.join(WORKSPACE_DIR, 'sample_config.json')
            if not os.path.exists(config_path):
                self.send_json_response(404, {"error": "Config not found"})
                return
            with open(config_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            input_data = load_from_dict(payload)
            ratio_mode = payload.get("category_ratio_mode", "target_load_scaling")
            solver = InvigilationSolver(input_data, ratio_mode=ratio_mode)
            result = solver.solve()
            report = solver.get_faculty_weekly_report(faculty_id, result, input_data)
            self.send_json_response(200, report)
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to get faculty report: {str(e)}"})

    def do_POST(self):
        if self.path == '/api/config':
            self.handle_post_config()
        elif self.path == '/api/solve':
            self.handle_post_solve()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_get_config(self):
        config_path = os.path.join(WORKSPACE_DIR, 'sample_config.json')
        if not os.path.exists(config_path):
            default_config = {
                "exam_type": "midsem",
                "category_ratio_mode": "target_load_scaling",
                "categories": [],
                "faculty_list": [],
                "sessions": [],
                "history": []
            }
            self.send_json_response(200, default_config)
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.send_json_response(200, data)
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to read config: {str(e)}"})

    def handle_post_config(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            config_data = json.loads(post_data.decode('utf-8'))

            config_path = os.path.join(WORKSPACE_DIR, 'sample_config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)

            # Keep solver_state.json updated in sync with UI saves
            state_path = os.path.join(WORKSPACE_DIR, 'solver_state.json')
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)

            self.send_json_response(200, {"success": True, "message": "Configuration saved successfully."})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to save config: {str(e)}"})

    def handle_post_solve(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))

            input_data = load_from_dict(payload)
            ratio_mode = payload.get("category_ratio_mode", "target_load_scaling")
            
            solver = InvigilationSolver(input_data, ratio_mode=ratio_mode)
            result = solver.solve()

            # If successful solve, persist history/imbalance data for next time
            if result.success:
                updated_history = []
                for summary in result.faculty_summaries:
                    updated_history.append({
                        "faculty_id": summary.faculty_id,
                        "previous_imbalance": summary.cumulative_imbalance
                    })
                
                config_path = os.path.join(WORKSPACE_DIR, 'sample_config.json')
                state_path = os.path.join(WORKSPACE_DIR, 'solver_state.json')
                
                current_config = {}
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            current_config = json.load(f)
                    except Exception as e:
                        print(f"Error loading sample_config.json for updating history: {e}")
                
                if not current_config:
                    current_config = payload
                
                current_config["history"] = updated_history
                
                try:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(current_config, f, indent=4)
                    with open(state_path, 'w', encoding='utf-8') as f:
                        json.dump(current_config, f, indent=4)
                    print("Updated and persisted solved history/imbalances.")
                except Exception as e:
                    print(f"Error persisting updated config: {e}")

            result_dict = asdict(result)
            self.send_json_response(200, result_dict)
        except Exception as e:
            self.send_json_response(500, {"error": f"Solver failed: {str(e)}"})

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        response_bytes = json.dumps(data).encode('utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

def run_server():
    os.chdir(WORKSPACE_DIR)
    
    # Run the Excel state bootstrap
    bootstrap_state()
    
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), InvigilationHandler) as httpd:
        print(f"Server successfully started at http://localhost:{PORT}")
        print("Press Ctrl+C to terminate.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            sys.exit(0)

if __name__ == "__main__":
    run_server()
