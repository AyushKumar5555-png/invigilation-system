from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

def create_future_roadmap_pdf():
    pdf_filename = "Invigilation_Future_Implementation_Roadmap.pdf"
    
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
        fontSize=20,
        leading=24,
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
    story.append(Paragraph("BIT MESRA Invigilation Scheduler", doc_title_style))
    story.append(Paragraph("Future Decoupled Architecture, Database Design & Cloud Deployment Blueprint", doc_subtitle_style))
    story.append(Spacer(1, 10))
    
    # 1. THE PRODUCTION DECOUPLED ARCHITECTURE
    story.append(Paragraph("1. Production Decoupled Architecture", section_heading))
    story.append(Paragraph("To support multiple concurrent administrators, prevent request timeouts during complex solver executions, and scale resources, we must migrate to a decoupled cloud-ready architecture:", body_style))
    story.append(Paragraph("• <b>Frontend Client (Vite + React.js):</b> Modern SPA client hosted on Amazon S3 and distributed via CloudFront CDN. Handles interactive grids, live diagnostics visualization, and JSON configurations state locally.", bullet_style))
    story.append(Paragraph("• <b>Backend API Server (FastAPI):</b> High-performance asynchronous API server processing user authorizations, database operations, and job dispatching. Generates automatic Swagger/OpenAPI documentation.", bullet_style))
    story.append(Paragraph("• <b>Task Queue (Celery + Redis):</b> Solver engine tasks are decoupled. FastAPI dispatches solver jobs to Redis (broker). A pool of Celery workers picks up the tasks asynchronously, executes optimization search, and saves results back to the database.", bullet_style))
    
    # 2. DATABASE SYSTEM SELECTION
    story.append(Paragraph("2. Database Engine & Schema Design", section_heading))
    story.append(Paragraph("<b>Database Selection:</b> <b>PostgreSQL (via Amazon RDS)</b> is chosen for its robustness, native JSONB support (useful for dynamic settings configurations), transactional safety (ACID compliance), and compatibility with SQLAlchemy ORM.", body_style))
    story.append(Paragraph("• <b>Model mapping:</b> Transition configurations and states to SQL tables:<br/>"
                           "  - <code>faculties</code> (stores emp codes, names, standardized categories, PG timetable exclusions).<br/>"
                           "  - <code>sessions</code> (stores slots details, duration hours, day indices, workloads).<br/>"
                           "  - <code>schedules</code> (stores calculated invigilator allocation details, coverage percents).<br/>"
                           "  - <code>history</code> (persists historical imbalances to allow continuous load balancing over multiple semesters).", bullet_style))
    
    story.append(PageBreak())
    
    # 3. PRODUCTION DEPLOYMENT STEPS
    story.append(Paragraph("3. Step-by-Step Deployment Pipeline", section_heading))
    story.append(Paragraph("The deployment steps are automated using Continuous Integration/Continuous Deployment (CI/CD):", body_style))
    
    story.append(Paragraph("<b>Step A: Containerization</b><br/>"
                           "Write multi-stage Dockerfiles to build optimized, lightweight images for the Frontend (distributing static assets via Nginx), API Server (FastAPI with production uvicorn server), and Worker Nodes (Celery task executor).", bullet_style))
    
    story.append(Paragraph("<b>Step B: Infrastructure provisioning (IaC)</b><br/>"
                           "Use Terraform to provision AWS resources inside a custom VPC: public subnets for the Application Load Balancer (ALB), and private subnets for ECS Fargate containers, Redis Cache, and RDS PostgreSQL database.", bullet_style))
    
    story.append(Paragraph("<b>Step C: CI/CD Pipeline (GitHub Actions)</b><br/>"
                           "On code push: (1) Run unit tests & code linters, (2) Build Docker images, (3) Push images to Amazon Elastic Container Registry (ECR), (4) Trigger ECS Fargate rolling updates to deploy code without downtime.", bullet_style))
    
    # 4. IMPLEMENTATION ROADMAP & TIMELINE
    story.append(Paragraph("4. Implementation Roadmap Timeline", section_heading))
    
    # Roadmap Table
    table_data = [
        [Paragraph("<b>Phase</b>", body_style), Paragraph("<b>Target Focus</b>", body_style), Paragraph("<b>Key Deliverables</b>", body_style)],
        [Paragraph("<b>Phase 1</b>", body_style), Paragraph("Backend Refactoring", body_style), Paragraph("FastAPI REST endpoints, Celery workers + Redis setup", body_style)],
        [Paragraph("<b>Phase 2</b>", body_style), Paragraph("Database & ORM", body_style), Paragraph("RDS PostgreSQL schema migrations via Alembic", body_style)],
        [Paragraph("<b>Phase 3</b>", body_style), Paragraph("SSO & Admin UI", body_style), Paragraph("JWT auth, LDAP/Active Directory SSO integration", body_style)],
        [Paragraph("<b>Phase 4</b>", body_style), Paragraph("DevOps & Launch", body_style), Paragraph("Terraform provision, GitHub Actions CI/CD setup", body_style)]
    ]
    
    t = Table(table_data, colWidths=[60, 180, 260])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    
    # Build
    doc.build(story)
    print(f"Roadmap PDF successfully created: {pdf_filename}")

if __name__ == "__main__":
    create_future_roadmap_pdf()
