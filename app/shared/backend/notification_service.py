"""
NexClaim Notification Service.

Creates in-app notifications and triggers email notifications
for all claim status changes.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.shared.backend.email_service import email_service
from app.shared.backend.models import Notification, User

logger = logging.getLogger(__name__)


class NotificationService:
    """Creates DB notifications and sends email alerts on claim events."""

    def notify_claim_status(
        self,
        db: Session,
        user: User,
        claim_id: int,
        status: str,
        message: str,
        reviewer_comments: Optional[str] = None,
        notification_type: str = "INFO",
    ) -> None:
        """Create an in-app notification and send a status email."""
        self._create_notification(
            db=db,
            user_id=user.id,
            title=f"Claim #{claim_id} Status Update: {status.replace('_', ' ')}",
            message=message,
            notification_type=notification_type,
        )
        email_service.send_claim_status_email(
            to_email=user.email,
            full_name=user.full_name,
            claim_id=claim_id,
            status=status,
            message=message,
            reviewer_comments=reviewer_comments,
        )

    def notify_reviewer(
        self,
        db: Session,
        reviewer_user: User,
        claim_id: int,
        action: str,
    ) -> None:
        """Notify a reviewer about a new claim or escalation."""
        self._create_notification(
            db=db,
            user_id=reviewer_user.id,
            title=f"Action Required: Claim #{claim_id}",
            message=action,
            notification_type="WARNING",
        )
        email_service.send_reviewer_notification_email(
            to_email=reviewer_user.email,
            reviewer_name=reviewer_user.full_name,
            claim_id=claim_id,
            action=action,
        )

    def notify_admin(
        self,
        db: Session,
        admin_user: User,
        claim_id: int,
        message: str,
    ) -> None:
        """Notify admin about an escalated claim."""
        self._create_notification(
            db=db,
            user_id=admin_user.id,
            title=f"Escalated Claim #{claim_id} Requires Review",
            message=message,
            notification_type="WARNING",
        )

    @staticmethod
    def _create_notification(
        db: Session,
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "INFO",
    ) -> None:
        """Insert a notification record into the database."""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
        db.add(notification)
        db.commit()
        logger.info("Notification created for user %d: %s", user_id, title)


notification_service = NotificationService()
