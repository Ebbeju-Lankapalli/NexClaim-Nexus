"""
NexClaim Email Service.

Sends transactional emails via Gmail SMTP using App Password.
Supports OTP emails and claim status notification emails.
"""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.shared.backend.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Handles all outbound email communication via Gmail SMTP."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.from_name = settings.FROM_NAME

    def _build_html_email(self, subject: str, html_body: str) -> MIMEMultipart:
        """Build a MIME multipart email message with HTML body."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        part = MIMEText(html_body, "html")
        msg.attach(part)
        return msg

    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send an HTML email to the specified recipient."""
        if not self.smtp_user or not self.smtp_password:
            logger.warning(
                "SMTP credentials not configured. Email to %s not sent.", to_email
            )
            logger.info("[DEV MODE] Email Subject: %s | To: %s", subject, to_email)
            return False

        try:
            msg = self._build_html_email(subject, html_body)
            msg["To"] = to_email
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())
            logger.info("Email sent successfully to %s", to_email)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed. Check App Password configuration.")
            return False
        except smtplib.SMTPException as exc:
            logger.error("Failed to send email to %s: %s", to_email, exc)
            return False

    def send_otp_email(self, to_email: str, full_name: str, otp_code: str) -> bool:
        """Send OTP verification email."""
        subject = "NexClaim – Verify Your Email Address"
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Inter, sans-serif; background: #F8FAF9; margin: 0; padding: 20px;">
          <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px;
                      box-shadow: 0 8px 32px rgba(124,154,146,0.15); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #7C9A92, #4F6F64); padding: 40px 30px; text-align: center;">
              <h1 style="color: #fff; font-family: Poppins, sans-serif; margin: 0; font-size: 28px;">NexClaim</h1>
              <p style="color: #DCE8E3; margin: 8px 0 0;">Insurance Claim Pre-Assessment Agent</p>
            </div>
            <div style="padding: 40px 30px;">
              <h2 style="color: #2C3E36; font-family: Poppins, sans-serif;">Email Verification</h2>
              <p style="color: #4F6F64;">Hello <strong>{full_name}</strong>,</p>
              <p style="color: #4F6F64;">Please use the following OTP to verify your email address.
                 This code expires in <strong>10 minutes</strong>.</p>
              <div style="text-align: center; margin: 30px 0;">
                <div style="background: linear-gradient(135deg, #DCE8E3, #F8FAF9); border: 2px solid #7C9A92;
                            border-radius: 12px; display: inline-block; padding: 20px 40px;">
                  <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px;
                               color: #2C3E36; font-family: Poppins, sans-serif;">{otp_code}</span>
                </div>
              </div>
              <p style="color: #4F6F64; font-size: 14px;">
                If you did not request this verification, please ignore this email.
              </p>
            </div>
            <div style="background: #F8FAF9; padding: 20px 30px; text-align: center;">
              <p style="color: #7C9A92; font-size: 12px; margin: 0;">© 2024 NexClaim. All rights reserved.</p>
            </div>
          </div>
        </body>
        </html>
        """
        return self.send_email(to_email, subject, html_body)

    def send_welcome_email(self, to_email: str, full_name: str, temp_password: str, login_url: str) -> bool:
        """Send welcome email with temporary password."""
        subject = "Welcome to NexClaim"
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Inter, sans-serif; background: #F8FAF9; margin: 0; padding: 20px;">
          <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px;
                      box-shadow: 0 8px 32px rgba(124,154,146,0.15); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #7C9A92, #4F6F64); padding: 40px 30px; text-align: center;">
              <h1 style="color: #fff; font-family: Poppins, sans-serif; margin: 0; font-size: 28px;">NexClaim</h1>
              <p style="color: #DCE8E3; margin: 8px 0 0;">Insurance Claim Pre-Assessment Agent</p>
            </div>
            <div style="padding: 40px 30px;">
              <h2 style="color: #2C3E36; font-family: Poppins, sans-serif;">Welcome to NexClaim!</h2>
              <p style="color: #4F6F64;">Hello <strong>{full_name}</strong>,</p>
              <p style="color: #4F6F64;">An administrator has created an account for you on the NexClaim platform.</p>
              <p style="color: #4F6F64;">You can log in using your email address and the following temporary password:</p>
              <div style="text-align: center; margin: 30px 0;">
                <div style="background: linear-gradient(135deg, #DCE8E3, #F8FAF9); border: 2px solid #7C9A92;
                            border-radius: 12px; display: inline-block; padding: 20px 40px;">
                  <span style="font-size: 24px; font-weight: 700; letter-spacing: 2px;
                               color: #2C3E36; font-family: monospace;">{temp_password}</span>
                </div>
              </div>
              <p style="color: #4F6F64;">You will be required to change your password upon your first login.</p>
              <p style="text-align: center; margin: 30px 0;">
                <a href="{login_url}" style="background: #5D8A66; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold;">Login to NexClaim</a>
              </p>
            </div>
            <div style="background: #F8FAF9; padding: 20px 30px; text-align: center;">
              <p style="color: #7C9A92; font-size: 12px; margin: 0;">© 2024 NexClaim. All rights reserved.</p>
            </div>
          </div>
        </body>
        </html>
        """
        return self.send_email(to_email, subject, html_body)

    def send_claim_status_email(
        self,
        to_email: str,
        full_name: str,
        claim_id: int,
        status: str,
        message: str,
        reviewer_comments: Optional[str] = None,
    ) -> bool:
        """Send claim status update notification email."""
        status_colors = {
            "SUBMITTED": "#7C9A92",
            "AI_PROCESSING": "#D6A85F",
            "UNDER_REVIEW": "#4F6F64",
            "APPROVED": "#2d8a4e",
            "REJECTED": "#c0392b",
            "ESCALATED": "#e67e22",
            "ADMIN_REVIEW": "#8e44ad",
        }
        color = status_colors.get(status, "#7C9A92")
        subject = f"NexClaim – Claim #{claim_id} Status Update: {status.replace('_', ' ')}"
        comments_section = (
            f'<div style="background: #F8FAF9; border-left: 4px solid #7C9A92; padding: 15px; margin-top: 20px;">'
            f'<strong style="color: #2C3E36;">Reviewer Comments:</strong>'
            f'<p style="color: #4F6F64; margin: 8px 0 0;">{reviewer_comments}</p></div>'
            if reviewer_comments
            else ""
        )
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Inter, sans-serif; background: #F8FAF9; margin: 0; padding: 20px;">
          <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px;
                      box-shadow: 0 8px 32px rgba(124,154,146,0.15); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #7C9A92, #4F6F64); padding: 40px 30px; text-align: center;">
              <h1 style="color: #fff; font-family: Poppins, sans-serif; margin: 0;">NexClaim</h1>
            </div>
            <div style="padding: 40px 30px;">
              <h2 style="color: #2C3E36; font-family: Poppins, sans-serif;">Claim Status Update</h2>
              <p style="color: #4F6F64;">Hello <strong>{full_name}</strong>,</p>
              <p style="color: #4F6F64;">Your claim <strong>#{claim_id}</strong> has been updated.</p>
              <div style="text-align: center; margin: 25px 0;">
                <span style="background: {color}; color: #fff; padding: 10px 30px; border-radius: 50px;
                             font-weight: 600; font-size: 16px; font-family: Poppins, sans-serif;">
                  {status.replace('_', ' ')}
                </span>
              </div>
              <p style="color: #4F6F64;">{message}</p>
              {comments_section}
            </div>
            <div style="background: #F8FAF9; padding: 20px 30px; text-align: center;">
              <p style="color: #7C9A92; font-size: 12px; margin: 0;">© 2024 NexClaim. All rights reserved.</p>
            </div>
          </div>
        </body>
        </html>
        """
        return self.send_email(to_email, subject, html_body)

    def send_reviewer_notification_email(
        self, to_email: str, reviewer_name: str, claim_id: int, action: str
    ) -> bool:
        """Send notification email to reviewer about a new claim or escalation."""
        subject = f"NexClaim – Action Required on Claim #{claim_id}"
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Inter, sans-serif; background: #F8FAF9; margin: 0; padding: 20px;">
          <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px;
                      box-shadow: 0 8px 32px rgba(124,154,146,0.15); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #7C9A92, #4F6F64); padding: 40px 30px; text-align: center;">
              <h1 style="color: #fff; font-family: Poppins, sans-serif; margin: 0;">NexClaim</h1>
            </div>
            <div style="padding: 40px 30px;">
              <h2 style="color: #2C3E36; font-family: Poppins, sans-serif;">Reviewer Notification</h2>
              <p style="color: #4F6F64;">Hello <strong>{reviewer_name}</strong>,</p>
              <p style="color: #4F6F64;">{action} for Claim <strong>#{claim_id}</strong>.</p>
              <p style="color: #4F6F64;">Please log in to the NexClaim Reviewer Portal to take action.</p>
            </div>
          </div>
        </body>
        </html>
        """
        return self.send_email(to_email, subject, html_body)


email_service = EmailService()
