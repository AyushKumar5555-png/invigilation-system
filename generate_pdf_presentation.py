from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

def create_presentation_pdf():
    pdf_filename = "Invigilation_Backend_Workflow.pdf"
    
    # Setup document in Landscape Letter size (representing slides)
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Palette
    c_primary = colors.HexColor("#0f3ba2")
    c_secondary = colors.HexColor("#1e40af")
    c_accent = colors.HexColor("#3b82f6")
    c_dark = colors.HexColor("#1e293b")
    c_light = colors.HexColor("#f8fafc")
    c_border = colors.HexColor("#cbd5e1")
    
    # Custom styles
    title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=c_primary,
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'SlideSubtitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=c_secondary,
        spaceAfter=10
    )
    
    body_style = ParagraphStyle(
        'SlideBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=c_dark
    )
    
    code_style = ParagraphStyle(
        'SlideCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0f172a")
    )
    
    story = []
    
    # ==================== SLIDE 1 ====================
    story.append(Paragraph("BIT MESRA Invigilation Scheduler", title_style))
    story.append(Paragraph("Backend Roster Bootstrapping & API Request Routing Lifecycle", subtitle_style))
    story.append(Spacer(1, 10))
    
    # Columns for Slide 1 layout
    # Left: Bootstrapping Flow, Right: HTTP/REST Endpoints
    col1_content = [
        Paragraph("<b>1. Server Startup & Bootstrapping Sequence</b>", subtitle_style),
        Paragraph("• <b>State Verification:</b> Server checks if <code>solver_state.json</code> exists to retain current running states.<br/>"
                  "• <b>Excel Fallback:</b> If state is missing, parses <i>'Faculty List (Emp. Code, Phone No. and E-mail ID).xlsx'</i>.<br/>"
                  "• <b>Data Normalization:</b> Extracts Empl. Code as string keys, standardizes designations (Professor, Associate, Assistant), and builds default history metrics (imbalance = 0.0).<br/>"
                  "• <b>State Lock:</b> Writes initialized dataset to <code>solver_state.json</code> and syncs <code>sample_config.json</code>.", body_style)
    ]
    
    col2_content = [
        Paragraph("<b>2. REST API Request Routing</b>", subtitle_style),
        Paragraph("• <b>GET /api/config:</b> Reads and returns active configurations to frontend dashboard.<br/>"
                  "• <b>POST /api/config:</b> Receives UI configuration payload, writes changes to disk, and updates <code>solver_state.json</code> to maintain persistence.<br/>"
                  "• <b>POST /api/solve:</b> Entry point for the scheduling solver. Parses payloads into dataclasses (<code>AllocationInput</code>) via <code>load_from_dict</code>, triggers the optimizer, and returns structured schedules (<code>AllocationResult</code>).", body_style)
    ]
    
    # Build Table layout for Slide 1
    slide1_table_data = [[col1_content, col2_content]]
    t1 = Table(slide1_table_data, colWidths=[360, 360])
    t1.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 12),
        ('BACKGROUND', (0,0), (-1,-1), c_light),
        ('BOX', (0,0), (-1,-1), 1.5, c_primary),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
    ]))
    
    story.append(t1)
    story.append(PageBreak())
    
    # ==================== SLIDE 2 ====================
    story.append(Paragraph("BIT MESRA Invigilation Scheduler", title_style))
    story.append(Paragraph("Core Invigilation Solver Optimization Pipeline", subtitle_style))
    story.append(Spacer(1, 10))
    
    col1_s2 = [
        Paragraph("<b>3. Target Workload & Initial Guess</b>", subtitle_style),
        Paragraph("• <b>Designation Scaling:</b> Computes expected duty weight-hours proportionally based on designation ratio multipliers (e.g. Prof=2.0, Assoc=3.0, Asst=4.0).<br/>"
                  "• <b>Historical Correction:</b> Adjusts targets dynamically by factoring in past workloads (+n hours for overload history).<br/>"
                  "• <b>Greedy Search:</b> Orders exam blocks chronologically and allocates slots to qualified faculty members with the lowest accumulated load.", body_style)
    ]
    
    col2_s2 = [
        Paragraph("<b>4. Constraint Validation & Local Search Optimization</b>", subtitle_style),
        Paragraph("• <b>Hard Constraints Enforcement:</b> Rejects allocations exceeding 1 shift/day, violating availability overrides, or clashing with PG lecture blocks.<br/>"
                  "• <b>Hill-Climbing Local Search:</b> Performs pairwise duty swaps to minimize fairness imbalances.<br/>"
                  "• <b>Fairness Verification:</b> Calculates Gini inequality coefficient & Jain's Fairness Index to compile diagnostics and return the optimal schedule.", body_style)
    ]
    
    slide2_table_data = [[col1_s2, col2_s2]]
    t2 = Table(slide2_table_data, colWidths=[360, 360])
    t2.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 12),
        ('BACKGROUND', (0,0), (-1,-1), c_light),
        ('BOX', (0,0), (-1,-1), 1.5, c_primary),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
    ]))
    
    story.append(t2)
    
    # Build Document
    doc.build(story)
    print(f"Presentation PDF successfully created: {pdf_filename}")

if __name__ == "__main__":
    create_presentation_pdf()
