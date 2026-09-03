# MedAudit Backend API
> Autonomous Medical Bill Auditing Engine · AWS Agents for Humans Hackathon

MedAudit is an autonomous background agent that ingests medical bills, cross-references CPT codes against Medicare fee schedules, detects upcoding and unbundling errors, and prepares regulatory dispute letters.

## Architecture

- **Framework**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL (via SQLAlchemy 2.0 async + Alembic)
- **Document OCR**: Amazon Textract (Key-Value Forms & Tables extraction)
- **Object Storage**: Amazon S3 (direct client presigned uploads)
- **Auth**: AWS Cognito JWT verification
- **Notifications**: AWS SES appeal letter dispatcher

---

## Getting Started

### 1. Setup Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Initialize & Seed Database
```bash
# Apply database migrations
alembic upgrade head

# Seed CMS Medicare baseline CPT codes & default policy rules
python -m backend.app.db.seeds.seed_cpt_codes
```

### 4. Run Locally
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation will be available at `http://localhost:8000/docs`.

---

## Running Tests
```bash
pytest backend/tests/ -v
```

---

## Docker Deployment
```bash
docker build -t medaudit-backend:latest -f backend/Dockerfile .
docker run -p 8000:8000 --env-file .env medaudit-backend:latest
```

## License
MIT License
