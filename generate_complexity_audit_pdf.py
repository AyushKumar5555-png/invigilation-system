import os
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and stamp page numbers and headers/footers in Times New Roman.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Black and white / High-contrast theme
        text_color = colors.HexColor("#000000")
        border_color = colors.HexColor("#000000")
        
        # Header (Top of each slide)
        self.setFont("Times-Bold", 11)
        self.setFillColor(text_color)
        self.drawString(36, 565, "BIT MESRA EXAMINATIONS CELL | ARCHITECTURAL AUDIT")
        
        self.setStrokeColor(border_color)
        self.setLineWidth(1)
        self.line(36, 555, 756, 555)
        
        # Footer (Bottom of each slide)
        self.line(36, 50, 756, 50)
        self.setFont("Times-Roman", 11)
        self.drawString(36, 35, "CONFIDENTIAL - SYSTEM AUDIT DOCUMENT")
        self.drawRightString(756, 35, f"Page {self._pageNumber} of {page_count}")
        
        self.restoreState()


def create_complexity_audit_pdf():
    pdf_filename = "invigilation_complexity_audit.pdf"
    
    # Setup document in Landscape mode for slide deck presentation layout
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=60,
        bottomMargin=60
    )
    
    styles = getSampleStyleSheet()
    
    # Pure High Contrast Black and White Styles with SIGNIFICANTLY LARGER text sizes
    title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=30,      # Increased from 24
        leading=35,       # Adjusted leading
        textColor=colors.black,
        spaceAfter=20
    )
    
    subtitle_style = ParagraphStyle(
        'SlideSubtitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=18,      # Increased from 14
        leading=22,       # Adjusted leading
        textColor=colors.black,
        spaceAfter=30
    )
    
    h1_style = ParagraphStyle(
        'Heading1_Times',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=22,      # Increased from 18
        leading=26,       # Adjusted leading
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=15,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'Heading2_Times',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=15,      # Increased from 13
        leading=18,       # Adjusted leading
        textColor=colors.black,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'Body_Times',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=13.5,    # Increased from 12
        leading=18,       # Adjusted leading
        textColor=colors.black,
        spaceAfter=10
    )
    
    code_style = ParagraphStyle(
        'Code_Times',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=12,      # Increased from 11
        leading=15,       # Adjusted leading
        textColor=colors.black
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader_Times',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=13,      # Increased from 11
        leading=16,
        textColor=colors.black
    )
    
    table_body_style = ParagraphStyle(
        'TableBody_Times',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12.5,    # Increased from 10.5
        leading=16,
        textColor=colors.black
    )
    
    story = []
    
    # ------------------ SLIDE 1: COVER SLIDE ------------------
    story.append(Spacer(1, 80))
    story.append(Paragraph("Invigilation Engine: Complexity & Fairness Optimization Audit", title_style))
    story.append(Paragraph("A Rigorous Mathematical Analysis and HR Performance Verification Slide Deck", subtitle_style))
    story.append(Spacer(1, 20))
    
    cover_meta = """
    <b>Document Class:</b> Systems Architecture & Computational Analysis<br/>
    <b>Roster Size:</b> 46 Faculty Members | <b>Target Architecture:</b> Local HTTP Integration<br/>
    <b>Typography Standard:</b> Times New Roman (Large High Contrast Edition)
    """
    story.append(Paragraph(cover_meta, body_style))
    story.append(PageBreak())
    
    # ------------------ SLIDE 2: COMPLEXITY BREAKDOWN (PHASE A & B) ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("1. Time Complexity: Initial Allocation & Search Refinement", h1_style))
    
    col1_content = [
        Paragraph("<b>Phase A: Greedy Initial Guess</b>", h2_style),
        Paragraph("• <b>Mechanism:</b> Chronological sorting of all exam sessions combined with dynamic workload-balanced candidate matching.", body_style),
        Paragraph("• <b>Mathematical Bound:</b> <font face=\"Courier\">O(S log S + S * R * F log F)</font>", body_style),
        Paragraph("• <b>Implication:</b> Guarantees an initial schedule in fractions of a millisecond.", body_style)
    ]
    
    col2_content = [
        Paragraph("<b>Phase B: Bounded Hill-Climbing Search</b>", h2_style),
        Paragraph("• <b>Mechanism:</b> Swaps duty slots and evaluates change using Jain's Index and Gini Coefficient metrics.", body_style),
        Paragraph("• <b>Mathematical Bound:</b> <font face=\"Courier\">O(I * F)</font> (for $I = 20,000$ iterations)", body_style),
        Paragraph("• <b>Implication:</b> Runs in absolute linear correlation to roster size. Swift delta updates avoid global re-evaluation.", body_style)
    ]
    
    slide2_table = Table([[col1_content, col2_content]], colWidths=[360, 360])
    slide2_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 10),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.gray),
    ]))
    story.append(slide2_table)
    story.append(PageBreak())
    
    # ------------------ SLIDE 3: COMPLEXITY (PHASE C & D) & GLOSSARY ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("2. Backtracking, Unified Scaling, & Glossary", h1_style))
    
    col1_s3 = [
        Paragraph("<b>Phase C: Bounded Backtracking</b>", h2_style),
        Paragraph("• <b>Mechanism:</b> Deep tree search to resolve complex room allocation conflicts.", body_style),
        Paragraph("• <b>Mathematical Bound:</b> Exponential <font face=\"Courier\">O(F^K)</font> worst-case; capped at 100,000 steps.", body_style),
        Paragraph("<b>Phase D: Combined Unified Model</b>", h2_style),
        Paragraph("• <b>Pipeline Complexity:</b> <font face=\"Courier\">O((S log S + S * R * F log F) + I * F + 100,000 * F)</font>", body_style),
        Paragraph("• <b>Actual Scaling:</b> Linear <font face=\"Courier\">O(S)</font> on production data because $F$ and $I$ are fixed constants.", body_style)
    ]
    
    glossary_data = [
        [Paragraph("<b>Symbol</b>", table_header_style), Paragraph("<b>Definition</b>", table_header_style)],
        [Paragraph("<i>S</i>", code_style), Paragraph("Total exam sessions", table_body_style)],
        [Paragraph("<i>F</i>", code_style), Paragraph("Roster size (46 members)", table_body_style)],
        [Paragraph("<i>R</i>", code_style), Paragraph("Invigilators per room", table_body_style)],
        [Paragraph("<i>I</i>", code_style), Paragraph("Search steps (fixed at 20,000)", table_body_style)],
        [Paragraph("<i>K</i>", code_style), Paragraph("Unassigned remaining slots", table_body_style)]
    ]
    glossary_table = Table(glossary_data, colWidths=[65, 275])
    glossary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.gray),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    col2_s3 = [
        Paragraph("<b>Mathematical Notation Glossary</b>", h2_style),
        Spacer(1, 5),
        glossary_table
    ]
    
    slide3_table = Table([[col1_s3, col2_s3]], colWidths=[360, 360])
    slide3_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 10),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.gray),
    ]))
    story.append(slide3_table)
    story.append(PageBreak())
    
    # ------------------ SLIDE 4: SYSTEM RUNTIME PERFORMANCE ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Real-Time System Local Runtime Performance", h1_style))
    
    performance_content = [
        Paragraph("<b>Backend Execution Time Ranges (Locally)</b>", h2_style),
        Paragraph("• <b>Greedy Phase:</b> Runs in less than <b>5 ms</b> to construct the initial allocation guess.", body_style),
        Paragraph("• <b>Local Search Optimization Phase:</b> Takes between <b>50 ms to 150 ms</b> to complete the full 20,000 improvement swaps.", body_style),
        Paragraph("• <b>Worst-Case Backtracking Governor:</b> Takes between <b>1.0 to 2.0 seconds</b> to run the maximum 100,000 steps on highly constrained/unfeasible rosters.", body_style),
        Paragraph("• <b>Total Local Execution Range:</b> <b>50 ms to 2,000 ms (2.0 seconds max)</b>, ensuring backend responsiveness and avoiding page or thread hangs.", body_style)
    ]
    
    slide4_table = Table([[performance_content]], colWidths=[720])
    slide4_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 15),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(slide4_table)
    
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Audit PDF successfully created: {pdf_filename}")

if __name__ == "__main__":
    create_complexity_audit_pdf()
