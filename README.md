# NexClaim — Insurance Claim Pre-Assessment Agent

An AI-assisted insurance claim pre-assessment platform designed to help policyholders submit claims, help reviewers evaluate supporting documents, and help administrators manage policies and users through a unified web application.

NexClaim combines document processing, structured field extraction, policy validation, risk scoring, explainable recommendations, and human review workflows. It is designed to support the claim assessment process—not to replace accountable human decision-making.

---

## Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [User Roles](#user-roles)
- [AI-Assisted Claim Workflow](#ai-assisted-claim-workflow)
- [Policy Document Processing](#policy-document-processing)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Run the Application](#run-the-application)
- [Application Routes](#application-routes)
- [Testing](#testing)
- [Security and Privacy](#security-and-privacy)
- [Current Scope and Limitations](#current-scope-and-limitations)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Insurance claim assessment often involves reviewing policy documents, checking claim information, validating coverage conditions, and preparing decisions for review. These steps can be time-consuming when information is spread across multiple documents.

**NexClaim** organizes this process into a role-based workflow. It extracts information from uploaded documents, compares claim details with policy data stored in the application, applies validation rules, calculates a risk score, and generates a pre-assessment summary for reviewers.

### Project Goals

- Make claim submission and status tracking easier for policyholders.
- Help administrators maintain policy information in a searchable repository.
- Reduce repetitive document-review work through OCR and field extraction.
- Apply consistent policy validation rules.
- Present risk indicators and understandable explanations to reviewers.
- Maintain role-based access and an auditable review workflow.

---

## Key Features

### Policyholder Portal
- Policyholder registration and account verification workflow.
- Secure authentication and role-based access.
- Claim submission with supporting document uploads.
- Claim status tracking.
- Access to available pre-assessment results and notifications.

### Reviewer Workspace
- View claims awaiting review.
- Inspect extracted claim information and validation results.
- Review risk indicators, confidence scores, and generated explanations.
- Record a review outcome or escalate a claim when further assessment is needed.

### Administration Console
- Manage policy records and policy documents.
- Manage application users and reviewer access.
- View and administer claim records.
- Support controlled policy and account-management workflows.

### Document Intelligence
- OCR-based text extraction from supported documents.
- Structured extraction of relevant policy and claim fields.
- Reuse of stored policy information during claim validation.
- Validation results that can be inspected as part of the review process.

### AI-Assisted Pre-Assessment
- Rule-based policy validation.
- Risk classification into LOW, MEDIUM, or HIGH categories.
- Recommendation generation for review workflows.
- Weighted confidence scoring.
- Natural-language explanations and reviewer-oriented summaries.

### Application and API
- FastAPI backend.
- Interactive API documentation.
- SQLAlchemy-based data access.
- Automated tests for key application modules.
- Container configuration for deployment experimentation.

---

## User Roles

| Role | Main Responsibilities |
|---|---|
| **Policyholder** | Register, submit claims, upload supporting documents, track claim status, and view available results. |
| **Reviewer** | Examine claim details, inspect validation and risk results, record review decisions, or escalate claims. |
| **Administrator** | Manage policies, users, reviewer access, and application records. |

Access to protected operations is controlled by authentication and role-based authorization. Production deployments should provision accounts securely and use unique credentials.

---

## AI-Assisted Claim Workflow

The following diagram describes the intended pre-assessment flow.

```text
Policyholder submits a claim
            |
            v
     Document upload
            |
            v
   OCR and text extraction
            |
            v
   Structured field extraction
            |
            v
   Retrieve stored policy data
            |
            v
    Policy rule validation
            |
            v
       Risk scoring
            |
            v
 Recommendation and confidence
            |
            v
 Explainable pre-assessment brief
            |
            v
      Human reviewer
            |
            v
 Review, decision, or escalation
```

### 1. Document Processing
Uploaded documents are processed using the available OCR and PDF text-extraction components. Extracted text is passed to the field-extraction module.

### 2. Field Extraction
The application attempts to identify relevant values such as policy identifiers, patient or claimant details, diagnoses, dates, and amounts. Extraction quality depends on document structure, scan quality, and the extraction rules.

### 3. Policy Validation
The claim's extracted information is compared with policy data already stored in the application. Validation rules identify conditions that may require attention.

### 4. Risk Scoring
A classification component assigns a risk category using the features available to the model. The score is an assessment aid and should be interpreted in context.

### 5. Recommendation and Explanation
The recommendation engine combines validation outcomes and risk indicators to produce a pre-assessment recommendation. Confidence scoring and natural-language explanations help reviewers understand the result.

### 6. Human Review
A reviewer examines the available evidence and records the appropriate workflow outcome. Automated recommendations should not be treated as a substitute for human review, applicable policy terms, or regulatory obligations.

---

## Policy Document Processing

Administrators can upload policy documents for processing.

```text
Policy document
      |
      v
 OCR / PDF text extraction
      |
      v
 Field extraction
      |
      v
 Structured policy record
      |
      v
 Stored policy data
      |
      v
 Reused during claim validation
```

Storing extracted policy information allows later claim checks to use the structured record rather than repeatedly processing the same source document. Extracted information should be reviewed for accuracy before being relied on in a consequential assessment.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI |
| Data validation | Pydantic |
| ORM / Database access | SQLAlchemy |
| Database | SQLite for local development |
| Authentication | JWT-based authentication |
| Password protection | Bcrypt-based password hashing |
| OCR | Tesseract OCR |
| PDF processing | `pypdf`, `pdf2image` |
| Risk classification | Scikit-learn-compatible model workflow |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Testing | pytest, FastAPI TestClient, pytest-cov |
| API documentation | OpenAPI, Swagger UI, ReDoc |
| Containerization | Docker |

Actual behavior and optional dependency availability depend on the project's installed packages and runtime configuration.

---

## Architecture

NexClaim is organized into feature-focused modules.

- **Shared backend:** configuration, database access, data models, schemas, authentication, notifications, and common API routes.
- **Policyholder module:** claim submission, document handling, and policyholder-facing workflows.
- **Reviewer module:** claim review, decision recording, and escalation workflows.
- **Admin module:** policy and user administration.
- **AI modules:** OCR, extraction, policy validation, risk scoring, recommendations, explanations, confidence scoring, and pre-assessment brief generation.
- **Frontend:** separate interfaces for the public landing page, policyholders, reviewers, and administrators.

The modular structure is intended to keep user-facing workflows separate from shared services and AI processing components.

---

## Project Structure

```text
NexClaim/
├── app/
│   ├── shared/
│   │   ├── backend/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── security.py
│   │   │   ├── email_service.py
│   │   │   ├── otp_service.py
│   │   │   ├── notification_service.py
│   │   │   └── router.py
│   │   └── frontend/
│   │       └── index.html
│   ├── policyholder/
│   │   ├── backend/router.py
│   │   └── frontend/dashboard.html
│   ├── reviewer/
│   │   ├── backend/router.py
│   │   └── frontend/dashboard.html
│   ├── admin/
│   │   ├── backend/router.py
│   │   └── frontend/dashboard.html
│   ├── ai/
│   │   ├── ocr/
│   │   ├── extraction/
│   │   ├── policy_validation/
│   │   ├── risk_scoring/
│   │   ├── recommendation_engine/
│   │   ├── explainability/
│   │   ├── confidence_scoring/
│   │   └── pre_assessment_brief/
│   ├── uploads/
│   │   ├── claims/
│   │   ├── medical_documents/
│   │   └── policy_repository/
│   └── main.py
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_ai_modules.py
│   ├── test_admin.py
│   ├── test_reviewer.py
│   └── test_policyholder.py
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
└── README.md
```

Some optional files or directories may differ depending on the project version.

---

## Getting Started

### Prerequisites

- Python 3.11 or another version supported by the project's dependencies.
- `pip`.
- Git (if cloning the repository).
- Tesseract OCR and Poppler when image/PDF OCR features require them.
- A configured local environment file.

### 1. Clone the Repository

```bash
git clone https://github.com/Ebbeju-Lankapalli/NexClaim-Nexus.git
cd NexClaim-Nexus
```

### 2. Create a Virtual Environment

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a local environment file:

```bash
cp .env.example .env
```

On Windows, copy `.env.example` to `.env` using File Explorer or PowerShell.

Open `.env` and configure the values required by your local setup. Generate a unique, high-entropy signing key for authentication. Do not commit `.env` or place real credentials in `.env.example`.

### 5. Install OCR Dependencies (Optional)

For the best results with scanned documents, install Tesseract OCR and Poppler for your operating system and ensure their executables are available to the application.

Text-based PDFs may be processed using PDF text extraction when supported. Image OCR quality depends on scan resolution, orientation, and document layout.

---

## Run the Application

From the project root, activate the virtual environment and run:

```bash
uvicorn app.main:app --reload
```

The development server will normally be available at:

- Application: `http://localhost:8000`
- OpenAPI / Swagger documentation: `http://localhost:8000/api/docs`
- ReDoc documentation: `http://localhost:8000/api/redoc`

These addresses are for local development. A production deployment requires appropriate hosting, HTTPS, secure configuration, persistent storage, and operational monitoring.

---

## Application Routes

| Route | Purpose |
|---|---|
| `/` | Public landing page |
| `/policyholder` | Policyholder interface |
| `/reviewer` | Reviewer interface |
| `/admin` | Administration interface |
| `/api/docs` | Interactive API documentation |
| `/api/redoc` | ReDoc API documentation |

Routes may require authentication or role-specific authorization. Confirm route behavior in the running application and its API configuration.

---

## Testing

Run the test suite from the project root:

```bash
pytest
```

To measure line coverage:

```bash
pytest --cov=app tests/ --cov-report=term-missing --cov-report=html
```

The HTML coverage report is written to `htmlcov/`.

Coverage goals should be treated as targets until the test suite has been executed and the measured results reviewed. Tests should include authentication and authorization, invalid uploads, extraction failures, policy-validation edge cases, risk-scoring behavior, and reviewer workflows.

---

## Security and Privacy

NexClaim may handle personally identifiable information, health-related documents, and insurance records. Treat all uploaded files and extracted content as sensitive.

Recommended safeguards include:

- Keep environment files, signing keys, and credentials out of version control.
- Use unique, securely provisioned credentials and rotate exposed secrets immediately.
- Do not use example credentials in a deployed environment.
- Enforce authentication and role-based authorization on protected operations.
- Validate file types, sizes, and upload paths.
- Keep uploaded documents and local databases out of public repositories and container images.
- Restrict access to stored documents and define retention and deletion procedures.
- Use HTTPS and secure deployment settings outside local development.
- Protect logs from accidentally recording personal data, authentication tokens, or sensitive document content.
- Review AI-generated outputs and extracted fields before relying on them.
- Maintain appropriate audit trails for consequential review actions.
- Back up persistent data securely and test recovery procedures.

This README does not constitute a security certification or a claim of regulatory compliance. A production deployment requires a separate security, privacy, and operational assessment.

---

## Current Scope and Limitations

- OCR and field extraction can be inaccurate on low-quality scans or unexpected document layouts.
- Rule-based validation is limited to the rules implemented in the application.
- Risk scores depend on model design, training data, and input quality.
- Confidence values should not be interpreted as guarantees of correctness.
- Recommendation outputs are intended to support human review.
- SQLite is suitable for local development and demonstrations; deployment requirements should determine whether a production database is needed.
- Production readiness depends on verified tests, secure configuration, access controls, monitoring, backup and recovery, and deployment review.

---

## Future Improvements

Potential areas for further development include:

- More robust document classification and extraction.
- Confidence-aware handling of missing or conflicting fields.
- Model evaluation, calibration, bias testing, and drift monitoring.
- Policy-rule versioning and explainable validation results.
- Stronger audit reporting and reviewer feedback workflows.
- PostgreSQL support and managed database migrations.
- Background processing for large documents.
- Automated CI checks for tests, code quality, dependency vulnerabilities, and secret detection.
- Operational monitoring, structured logging, and secure document-retention workflows.

---

## Contributing

Contributions and suggestions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes and add or update tests.
4. Run the test suite.
5. Submit a pull request describing the change and its impact.

Do not include real credentials, personal data, medical documents, insurance records, or production database files in commits or issue reports.

---

## License

No license is specified in this README. Add a `LICENSE` file before explicitly granting permissions for reuse, modification, or redistribution.

---

**NexClaim — structured, explainable, AI-assisted insurance claim pre-assessment with human review.**
