"""
NexClaim – Insurance Claim Pre-Assessment Agent.

Application entry point. Configures FastAPI app, database initialization,
default role seeding, admin/reviewer seed accounts, and all routers.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# Configure logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

from app.shared.backend.config import settings
from app.shared.backend.database import Base, SessionLocal, engine
from app.shared.backend.models import Admin, Policyholder, Reviewer, Role, User
from app.shared.backend.security import hash_password, validate_password_strength

# Routers
from app.shared.backend.router import router as auth_router
from app.policyholder.backend.router import router as policyholder_router
from app.reviewer.backend.router import router as reviewer_router
from app.admin.backend.router import router as admin_router

# ---------------------------------------------------------------------------
# Upload directories
# ---------------------------------------------------------------------------

UPLOAD_DIRS = [
    "app/uploads/claims",
    "app/uploads/medical_documents",
    "app/uploads/policy_repository",
]


def _ensure_upload_directories() -> None:
    """Create required upload directories if they do not exist."""
    for directory in UPLOAD_DIRS:
        os.makedirs(directory, exist_ok=True)
    logger.info("Upload directories ready")


# ---------------------------------------------------------------------------
# Database seeding
# ---------------------------------------------------------------------------

def _seed_roles(db: Session) -> dict:
    """Ensure the three system roles exist. Return role name -> Role mapping."""
    roles = {}
    for role_name in ("policyholder", "reviewer", "admin"):
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name)
            db.add(role)
            db.flush()
            logger.info("Role created: %s", role_name)
        roles[role_name] = role
    db.commit()
    return roles


def _seed_admin(db: Session, roles: dict) -> None:
    """Create an admin only when explicit local seed credentials are configured."""
    if not settings.ADMIN_EMAIL.strip() or not settings.ADMIN_PASSWORD.strip():
        logger.warning("Admin seed skipped: configure ADMIN_EMAIL and ADMIN_PASSWORD in .env if needed")
        return
    if (len(settings.ADMIN_PASSWORD) < 12 or not validate_password_strength(settings.ADMIN_PASSWORD)
            or settings.ADMIN_PASSWORD.lower().startswith(("replace_", "change_me", "changeme", "your_"))):
        raise RuntimeError("ADMIN_PASSWORD must be a unique password of at least 12 characters with upper/lowercase, a digit, and a special character")
    existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
    if existing:
        return

    admin_role = roles.get("admin")
    if not admin_role:
        logger.error("Admin role not found — cannot seed admin account")
        return

    user = User(
        full_name=settings.ADMIN_NAME,
        email=settings.ADMIN_EMAIL,
        hashed_password=hash_password(settings.ADMIN_PASSWORD),
        role_id=admin_role.id,
        is_active=True,
        is_verified=True,
        first_login=False,
    )
    db.add(user)
    db.flush()

    admin = Admin(user_id=user.id)
    db.add(admin)
    db.commit()
    logger.info("Configured admin seed account created: %s", settings.ADMIN_EMAIL)


def _seed_reviewer(db: Session, roles: dict) -> None:
    """Create a reviewer only when explicit local seed credentials are configured."""
    if not settings.REVIEWER_EMAIL.strip() or not settings.REVIEWER_PASSWORD.strip():
        logger.warning("Reviewer seed skipped: configure REVIEWER_EMAIL and REVIEWER_PASSWORD in .env if needed")
        return
    if (len(settings.REVIEWER_PASSWORD) < 12 or not validate_password_strength(settings.REVIEWER_PASSWORD)
            or settings.REVIEWER_PASSWORD.lower().startswith(("replace_", "change_me", "changeme", "your_"))):
        raise RuntimeError("REVIEWER_PASSWORD must be a unique password of at least 12 characters with upper/lowercase, a digit, and a special character")
    existing = db.query(User).filter(User.email == settings.REVIEWER_EMAIL).first()
    if existing:
        return

    reviewer_role = roles.get("reviewer")
    if not reviewer_role:
        logger.error("Reviewer role not found")
        return

    user = User(
        full_name=settings.REVIEWER_NAME,
        email=settings.REVIEWER_EMAIL,
        hashed_password=hash_password(settings.REVIEWER_PASSWORD),
        role_id=reviewer_role.id,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.flush()

    reviewer = Reviewer(
        user_id=user.id,
        employee_id="EMP001",
        department="Claims Review",
        is_active=True,
    )
    db.add(reviewer)
    db.commit()
    logger.info("Configured reviewer seed account created: %s", settings.REVIEWER_EMAIL)


def _initialize_database() -> None:
    """Create all tables and seed required initial data."""
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")

    db = SessionLocal()
    try:
        roles = _seed_roles(db)
        _seed_admin(db, roles)
        _seed_reviewer(db, roles)
        logger.info("Database initialization complete")
    except Exception as exc:
        logger.error("Database initialization error: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

def _validate_security_configuration() -> None:
    """Fail closed when the JWT signing key is missing or obviously unsafe."""
    secret = settings.SECRET_KEY.strip()
    if len(secret) < 32 or secret.lower().startswith(("replace_", "change_this", "your-", "your_")):
        raise RuntimeError(
            "SECRET_KEY is missing or insecure. Set a random value of at least 32 characters in .env; "
            "generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application startup and shutdown lifecycle manager."""
    logger.info("Starting NexClaim v%s...", settings.APP_VERSION)
    _validate_security_configuration()
    _ensure_upload_directories()
    _initialize_database()
    logger.info("NexClaim is ready. Visit http://localhost:8000")
    yield
    logger.info("NexClaim shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NexClaim API",
    description="Insurance Claim Pre-Assessment Agent API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(policyholder_router)
app.include_router(reviewer_router)
app.include_router(admin_router)

# ---------------------------------------------------------------------------
# Static files & frontend routing
# ---------------------------------------------------------------------------

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

FRONTEND_ROOT = os.path.dirname(__file__)


@app.get("/", include_in_schema=False)
async def serve_landing():
    """Serve the landing page."""
    landing_path = os.path.join(FRONTEND_ROOT, "shared", "frontend", "index.html")
    if os.path.isfile(landing_path):
        return FileResponse(landing_path)
    return {"message": "Landing page not found."}


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    """Dummy favicon to prevent 404 errors."""
    return Response(status_code=204)


@app.get("/partner", include_in_schema=False)
async def serve_partner():
    """Serve the partner page."""
    partner_path = os.path.join(FRONTEND_ROOT, "shared", "frontend", "partner.html")
    if os.path.isfile(partner_path):
        return FileResponse(partner_path)
    return {"message": "Partner page not found."}


@app.get("/help", include_in_schema=False)
async def serve_help():
    """Serve the help page."""
    path = os.path.join(FRONTEND_ROOT, "shared", "frontend", "help.html")
    if os.path.isfile(path):
        return FileResponse(path)
    return {"message": "Help page not found."}


@app.get("/contact", include_in_schema=False)
async def serve_contact():
    """Serve the contact page."""
    path = os.path.join(FRONTEND_ROOT, "shared", "frontend", "contact.html")
    if os.path.isfile(path):
        return FileResponse(path)
    return {"message": "Contact page not found."}


@app.get("/policyholder", include_in_schema=False)
async def serve_policyholder_dashboard():
    """Serve the policyholder dashboard."""
    return FileResponse(
        os.path.join(FRONTEND_ROOT, "policyholder", "frontend", "dashboard.html")
    )


@app.get("/reviewer", include_in_schema=False)
async def serve_reviewer_dashboard():
    """Serve the reviewer dashboard."""
    return FileResponse(
        os.path.join(FRONTEND_ROOT, "reviewer", "frontend", "dashboard.html")
    )


@app.get("/admin", include_in_schema=False)
async def serve_admin_dashboard():
    """Serve the admin dashboard."""
    return FileResponse(
        os.path.join(FRONTEND_ROOT, "admin", "frontend", "dashboard.html")
    )


@app.get("/health", tags=["System"])
async def health_check():
    """Application health check endpoint."""
    return {"status": "healthy", "version": settings.APP_VERSION, "app": settings.APP_NAME}