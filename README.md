# NexClaim — Insurance Claim Pre-Assessment Agent

NexClaim is an AI-assisted insurance claim pre-assessment application built with FastAPI, SQLAlchemy, OCR, policy validation, risk scoring, reviewer workflows, and an HTML/CSS/JavaScript interface. It is a development/portfolio project; review and harden its deployment configuration before using real personal, medical, or insurance data. AI recommendations are decision support for qualified human reviewers, not an automatic final claim decision.

## Quick start

### 1. Create an environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `SECRET_KEY` in `.env`. Never commit `.env`, SMTP credentials, JWT signing keys, production passwords, databases, or uploaded documents. `.env.example` contains placeholders only.

For initial admin/reviewer accounts, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`, and optionally `REVIEWER_EMAIL` and `REVIEWER_PASSWORD`, in your local `.env` **before the first startup**. Seed passwords must be unique, at least 12 characters, and contain uppercase/lowercase letters, a digit, and a special character. If these variables are blank, those seed accounts are not created. There are no built-in default login credentials.

For Gmail SMTP, use a dedicated Gmail App Password (not your normal Google password) and set `SMTP_USER`, `SMTP_PASSWORD`, and `FROM_EMAIL`. If SMTP is not configured, email delivery will not work. For local-only testing, setting `DEBUG=true` permits OTPs to be written to the console when SMTP is absent; never enable this on a deployed system.

### 3. Run

```bash
uvicorn app.main:app --reload
```

The application validates that `SECRET_KEY` is configured with a random value of at least 32 characters before startup.

## Application URLs

| URL | Description |
|---|---|
| `http://localhost:8000/` | Landing page |
| `http://localhost:8000/policyholder` | Policyholder dashboard |
| `http://localhost:8000/reviewer` | Reviewer dashboard |
| `http://localhost:8000/admin` | Admin console |
| `http://localhost:8000/api/docs` | Swagger API documentation |
| `http://localhost:8000/api/redoc` | ReDoc API documentation |

CORS is restricted to the local origins listed in `CORS_ALLOWED_ORIGINS`. If your front end is hosted elsewhere, configure only the exact trusted origins in `.env`; do not use `*` with credentials.

## Project structure

```text
NexClaim/
├── app/
│   ├── shared/backend/       # Settings, DB models, auth, OTP, email, API routes
│   ├── shared/frontend/      # Public pages
│   ├── policyholder/         # Claim submission and policyholder UI
│   ├── reviewer/             # Claim review and reviewer UI
│   ├── admin/                # Admin APIs and console
│   ├── ai/                   # OCR, extraction, validation, risk, explanations
│   ├── static/               # Shared static assets and translations
│   └── main.py               # FastAPI entry point
├── tests/                    # API and AI pipeline tests
├── helm_chart/               # Optional Kubernetes chart templates
├── .env.example              # Safe environment template
├── .gitignore                # Excludes secrets, databases, and uploads
├── .dockerignore             # Excludes secrets and local data from build context
├── Dockerfile
└── requirements.txt
```

## AI-assisted claim pipeline

1. An administrator uploads a policy PDF/image. OCR and field extraction process the document; extracted policy information is stored for later validation.
2. A policyholder submits claim documents. The application extracts relevant fields and looks up the stored policy.
3. Policy rules are evaluated, then risk scoring, recommendation, confidence scoring, and an explanatory pre-assessment brief are produced.
4. Reviewers assess the output and make the final human decision.
5. Notifications are sent when SMTP is configured.

OCR/extraction errors and uncertain fields should be reviewed by a human. Risk scores and confidence values are estimates, not guarantees.

## Security notes

- `.env` and environment-specific files are excluded from Git and Docker build contexts. Keep real values only in local environment configuration or a managed secret store.
- Seed accounts are opt-in and require explicitly configured strong passwords. Do not reuse test or example passwords in deployments.
- OTP values are not logged except in explicit local `DEBUG=true` mode when SMTP is unavailable. Never enable that mode in a deployment.
- CORS uses an explicit allowlist. Configure `CORS_ALLOWED_ORIGINS` for your trusted deployment origins.
- Local databases and all claim, medical, and policy uploads are ignored by Git and Docker. Do not use real personal data in a public demo repository.
- If a secret has ever been pushed to a remote repository, rotate/revoke it. Deleting it in a later commit does not remove it from earlier Git history.
- Before production use, configure HTTPS, secure secret management, database migrations/backups, rate limiting, monitoring, access reviews, upload malware/content scanning, and an appropriate privacy/compliance review.

## OCR dependencies

For scanned PDFs/images, install Tesseract OCR and Poppler. Text-based PDFs may be processed using the `pypdf` fallback.

## Tests

```bash
pytest --cov=app tests/ --cov-report=html
```

Report measured test coverage rather than treating any target as a verified result.

## Stack

- FastAPI / Uvicorn
- SQLAlchemy / SQLite for local development
- JWT authentication and bcrypt password hashing
- Tesseract, pdf2image, pypdf, and Pillow for document processing
- HTML5, CSS3, and vanilla JavaScript

---

NexClaim is intended as an AI-assisted pre-assessment tool. Do not rely on model output alone for insurance claim decisions.
# NexClaim-Nexus
