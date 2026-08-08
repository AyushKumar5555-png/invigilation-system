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
        
        # Black and white / High-contrast gray theme
        text_color = colors.HexColor("#000000")
        border_color = colors.HexColor("#000000")
        
        # Header (Top of each slide)
        self.setFont("Times-Bold", 10)
        self.setFillColor(text_color)
        self.drawString(36, 570, "BIT MESRA EXAMINATIONS CELL | OPERATOR GUIDE")
        
        self.setStrokeColor(border_color)
        self.setLineWidth(1)
        self.line(36, 562, 756, 562)
        
        # Footer (Bottom of each slide)
        self.line(36, 45, 756, 45)
        self.setFont("Times-Roman", 10)
        self.drawString(36, 30, "SYSTEM MANUAL - FOR ACADEMIC OFFICE STAFF")
        self.drawRightString(756, 30, f"Page {self._pageNumber} of {page_count}")
        
        self.restoreState()


def create_user_manual_pdf():
    # Write to the specific file name Invigilation_System_User_Manual.pdf
    pdf_filename = "Invigilation_System_User_Manual.pdf"
    
    # Setup document in Landscape mode for slide deck presentation layout
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Pure High Contrast Black and White Styles using Times New Roman (Times-Roman / Times-Bold)
    title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.black,
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'SlideSubtitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.black,
        spaceAfter=25
    )
    
    h1_style = ParagraphStyle(
        'Heading1_Times',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.black,
        spaceBefore=10,
        spaceAfter=15,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'Heading2_Times',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.black,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'Body_Times',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12,
        leading=16,
        textColor=colors.black,
        spaceAfter=8
    )
    
    story = []
    
    # ------------------ SLIDE 1: COVER SLIDE ------------------
    story.append(Spacer(1, 100))
    story.append(Paragraph("Invigilation System: Operations & User Manual", title_style))
    story.append(Paragraph("A Step-by-Step Operator Guide for Academic Administration Staff", subtitle_style))
    story.append(Spacer(1, 20))
    
    cover_meta = """
    <b>Document Class:</b> Software Operations & Training Guide<br/>
    <b>Prerequisites:</b> No programming skill required (Point-and-Click interface)<br/>
    <b>Deployment Server:</b> <font face=\"Courier\">http://localhost:8080</font>
    """
    story.append(Paragraph(cover_meta, body_style))
    story.append(PageBreak())
    
    # ------------------ SLIDE 2: STARTUP & INITIALIZATION ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("1. Starting up the Scheduler Website", h1_style))
    
    col1_content = [
        Paragraph("<b>Step 1: Open the Application Folder</b>", h2_style),
        Paragraph("• Open the folder named <b>IIT Bombay</b> on your computer's Desktop.", body_style),
        Paragraph("• Locate the file named <b><code>start_invigilation_server.bat</code></b> (identifiable by a cog/gear icon or Windows Batch File type).", body_style)
    ]
    
    col2_content = [
        Paragraph("<b>Step 2: Start and Access</b>", h2_style),
        Paragraph("• <b>Double-click the file:</b> A black window will briefly pop up and minimize.", body_style),
        Paragraph("• <b>Web Browser Opens:</b> Your default browser will load the portal automatically at: <br/><b>http://localhost:8080</b>", body_style),
        Paragraph("• <b>Automated Roster:</b> All 46 faculty members are loaded automatically from the Excel template sheet.", body_style)
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
    
    # ------------------ SLIDE 3: NAVIGATION & SETTINGS ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("2. Customizing Faculty & Exam Sessions", h1_style))
    
    col1_s3 = [
        Paragraph("<b>Faculty Roster Customization</b>", h2_style),
        Paragraph("• <b>Availability Checks:</b> Select a teacher and uncheck specific session dates to mark leaves or out-of-station blocks.", body_style),
        Paragraph("• <b>Lecture Conflict Blocks:</b> Check slots under PG Timetable Blocks to ensure teachers are not scheduled during their classes.", body_style),
        Paragraph("• <b>Autosave Sync:</b> All checkboxes are saved to the storage disk instantly.", body_style)
    ]
    
    col2_s3 = [
        Paragraph("<b>Exam Sessions Setup</b>", h2_style),
        Paragraph("• <b>Exams Configuration:</b> Create new exam dates, select Morning/Afternoon sessions, input course codes, and assign rooms.", body_style),
        Paragraph("• <b>Staff Capacity:</b> Specify the exact number of required invigilator personnel needed for each room.", body_style)
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
    
    # ------------------ SLIDE 4: SOLVE & TROUBLESHOOTING ------------------
    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Generating Duties & Simple Troubleshooting", h1_style))
    
    col1_s4 = [
        Paragraph("<b>Generating the Schedule Grid</b>", h2_style),
        Paragraph("• <b>One-Click Solve:</b> Click the blue <b>▶️ Run Allocation</b> button at the top right.", body_style),
        Paragraph("• <b>Fair Distribution:</b> The engine runs optimization algorithms to allocate duties proportionally, satisfying all constraints in under 2 seconds.", body_style),
        Paragraph("• <b>Verify Fairness:</b> Review Jain's Index dial (targets close to 1.00) to confirm equitable load balance.", body_style)
    ]
    
    col2_s4 = [
        Paragraph("<b>Troubleshooting Errors</b>", h2_style),
        Paragraph("• <b>Unfeasible Schedule Warning:</b> If a red warning appears saying <i>'Solver failed to generate a feasible allocation'</i>, too many teachers are blocked from duty.", body_style),
        Paragraph("• <b>Resolution:</b> Go back to the Faculty Roster tab, unblock leaves or suspend PG lecture clashes for highly restricted faculty, then re-run allocation.", body_style)
    ]
    
    slide4_table = Table([[col1_s4, col2_s4]], colWidths=[360, 360])
    slide4_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 10),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.gray),
    ]))
    story.append(slide4_table)
    
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"User Manual PDF successfully created: {pdf_filename}")

if __name__ == "__main__":
    create_user_manual_pdf()
