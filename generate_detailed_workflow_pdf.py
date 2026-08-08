from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

def create_detailed_pdf():
    pdf_filename = "Invigilation_Detailed_System_Workflow.pdf"
    
    # Setup document in Portrait Letter size (representing a detailed report)
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Palette
    c_primary = colors.HexColor("#0f3ba2")
    c_secondary = colors.HexColor("#1e40af")
    c_accent = colors.HexColor("#3b82f6")
    c_dark = colors.HexColor("#1e293b")
    c_light = colors.HexColor("#f8fafc")
    c_border = colors.HexColor("#cbd5e1")
    
    # Styles
    doc_title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=c_primary,
        spaceAfter=6
    )
    
    doc_subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=c_accent,
        spaceAfter=20
    )
    
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=c_secondary,
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=c_dark,
        spaceAfter=8
    )
    
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )
    
    story = []
    
    # Header Title Area
    story.append(Paragraph("BIT MESRA Invigilation Duty Allocation System", doc_title_style))
    story.append(Paragraph("End-to-End System Execution & Implementation Workflow Walkthrough", doc_subtitle_style))
    story.append(Spacer(1, 10))
    
    # PAGE 1: SYSTEM INITIATION AND BOOTSTRAP LIFECYCLE
    story.append(Paragraph("1. Server Startup & Excel Bootstrapping Sequence", section_heading))
    story.append(Paragraph("The system boot lifecycle begins on the backend server side using <code>server.py</code>:", body_style))
    story.append(Paragraph("• <b>Roster Verification:</b> The server calls the <code>bootstrap_state()</code> routine on startup. It searches for <code>solver_state.json</code> in the workspace directory.", bullet_style))
    story.append(Paragraph("• <b>Excel Data Extraction:</b> If the json state is missing, it reads the spreadsheet file <i>'Faculty List (Emp. Code, Phone No. and E-mail ID).xlsx'</i> (specifically from the sheet <i>'Seniority Wise List'</i>) as the absolute ground truth.", bullet_style))
    story.append(Paragraph("• <b>Roster Parsing & Normalization:</b> It maps Employee Code to <code>id</code> (safeguarding leading zeros), Faculty Member to <code>name</code>, and Designation to <code>category</code> (standardizing values to Professor, Associate Professor, and Assistant Professor). Spacers and header rows are discarded.", bullet_style))
    story.append(Paragraph("• <b>Persistent State Cache:</b> A default history record (previous load imbalance = 0.0) is built for all 45 faculty members. These rosters are combined with configured session schedules and written to <code>solver_state.json</code> (for state replication) and <code>sample_config.json</code> (active web config) before binding socketserver to Port 8080.", bullet_style))
    
    story.append(Paragraph("2. Web Page Resource Loading Lifecycle", section_heading))
    story.append(Paragraph("Once the HTTP server is bound and active:", body_style))
    story.append(Paragraph("• <b>Asset Fetching:</b> The user opens <code>http://localhost:8080</code>. The browser downloads the static files: <code>index.html</code> (dashboard layouts), <code>index.css</code> (styles and colors), and <code>app.js</code> (state controller).", bullet_style))
    story.append(Paragraph("• <b>DOM Ready Callback:</b> The browser fires the <code>DOMContentLoaded</code> listener, which initializes navigation controls and invokes <code>loadConfigFromBackend()</code>.", bullet_style))
    
    story.append(Paragraph("3. Configuration Loading & UI Synchronization", section_heading))
    story.append(Paragraph("Before the user runs an allocation, the UI must match the server state:", body_style))
    story.append(Paragraph("• <b>GET /api/config:</b> The frontend queries the backend via a GET request. The backend reads <code>sample_config.json</code> and sends back the active configuration payload.", bullet_style))
    story.append(Paragraph("• <b>UI State Alignment:</b> <code>app.js</code> checks and normalizes category fields. It updates dashboard widgets, displaying the 45 synced faculty members and session counts on stats cards, then triggers a silent solver execution to pre-populate the calendar grid.", bullet_style))
    
    story.append(PageBreak())
    
    # PAGE 2: SOLVER OPTIMIZATION PIPELINE AND AUTOSAVE STATE PERSISTENCE
    story.append(Paragraph("4. Invoking the Scheduler Solver Engine", section_heading))
    story.append(Paragraph("• <b>POST /api/solve:</b> When the user clicks <b>Run Allocation</b>, the frontend gathers all active parameters from memory and posts them in JSON format to <code>/api/solve</code>.", bullet_style))
    story.append(Paragraph("• <b>Dataclass Parsing:</b> The backend handler parses the input into Python dataclasses (<code>AllocationInput</code>) via the <code>load_from_dict()</code> mapping function and instantiates the <code>InvigilationSolver</code> engine.", bullet_style))
    
    story.append(Paragraph("5. Solver Optimization Pipeline (invigilation_scheduler.py)", section_heading))
    story.append(Paragraph("The core solver engine executes a multi-layered optimization pipeline:", body_style))
    story.append(Paragraph("• <b>Category Target Calculations:</b> Computes expected duty weight-hours based on designation ratio multipliers (Professor = 2.0, Associate = 3.0, Assistant = 4.0), adjusted dynamically for historical load imbalances (adding +n hours if they were overloaded historically).", bullet_style))
    story.append(Paragraph("• <b>Greedy Initial Allocation:</b> Sorts all sessions chronologically. For each slot, it assigns the faculty member who currently has the lowest accumulated load.", bullet_style))
    story.append(Paragraph("• <b>Hard Constraint Validation:</b> Verifies that no assignment violates hard constraints: <i>(1) Max 1 shift per day per faculty</i>, <i>(2) No assignments during marked availability overrides</i>, <i>(3) No assignments during PG timetable class blocks</i>.", bullet_style))
    story.append(Paragraph("• <b>Local Search Swaps:</b> Performs iterative pairwise swaps of duties. Swaps are locked only if they reduce overall workload inequality (calculated using Gini Inequality Coefficient and Jain's Fairness Index) or resolve an unfilled slot. It halts once a local minimum is reached.", bullet_style))
    
    story.append(Paragraph("6. Dashboard Rendering Flow", section_heading))
    story.append(Paragraph("• <b>Serialization:</b> The solver returns the <code>AllocationResult</code> dataclass. The backend serializes it using <code>asdict()</code> and returns it as a JSON payload to the browser.", bullet_style))
    story.append(Paragraph("• <b>Grid Update:</b> <code>app.js</code> renders each grid cell on the timetable dashboard (populating course codes, rooms, and assigned faculty names). It also updates fairness dials, workload charts, and statistics widgets.", bullet_style))
    
    story.append(Paragraph("7. Autosave Trigger & State Persistence", section_heading))
    story.append(Paragraph("• <b>Autosave:</b> Every time the user interacts with settings, edits faculty details, or checks availability override boxes, the frontend immediately fires a silent <code>POST /api/config</code>.", bullet_style))
    story.append(Paragraph("• <b>Data Persistence:</b> The backend receives the payload and overwrites both <code>sample_config.json</code> and <code>solver_state.json</code> on disk. This prevents any data loss from server restarts or laptop shutdown cycles.", bullet_style))
    
    # Build Document
    doc.build(story)
    print(f"Detailed Workflow PDF successfully created: {pdf_filename}")

if __name__ == "__main__":
    create_detailed_pdf()
