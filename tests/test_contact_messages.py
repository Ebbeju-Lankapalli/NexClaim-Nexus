import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.shared.backend.models import ContactMessage
from tests.conftest import TestingSessionLocal

client = TestClient(app)

def test_submit_contact_message():
    response = client.post(
        "/api/auth/contact",
        json={
            "full_name": "John Doe",
            "email": "johndoe@example.com",
            "subject": "Login Issue",
            "message": "I cannot login to my account."
        }
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Your message has been sent successfully. We will get back to you soon!"

    # Verify it exists in DB
    db = TestingSessionLocal()
    msg = db.query(ContactMessage).filter(ContactMessage.email == "johndoe@example.com").first()
    assert msg is not None
    assert msg.full_name == "John Doe"
    assert msg.subject == "Login Issue"
    assert msg.status == "NEW"
    db.close()

def test_admin_get_contact_messages(auth_headers):
    # Ensure there is a message
    db = TestingSessionLocal()
    if not db.query(ContactMessage).first():
        new_msg = ContactMessage(
            full_name="Admin Test",
            email="admin.test@example.com",
            subject="Test",
            message="Test Msg"
        )
        db.add(new_msg)
        db.commit()
    db.close()

    response = client.get("/api/admin/contact-messages", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "full_name" in data[0]

def test_admin_get_contact_message_stats(auth_headers):
    response = client.get("/api/admin/contact-messages/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "unread" in data
    assert "resolved" in data
    assert "resolved" in data

def test_admin_update_contact_message(auth_headers):
    # Create a message to update
    db = TestingSessionLocal()
    new_msg = ContactMessage(
        full_name="Update Test",
        email="update.test@example.com",
        subject="Test Update",
        message="Test Update Msg"
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    msg_id = new_msg.id
    db.close()

    response = client.patch(
        f"/api/admin/contact-messages/{msg_id}",
        json={
            "status": "Resolved",
            "priority": "High",
            "admin_notes": "Fixed this issue"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Resolved"
    assert data["priority"] == "High"
    assert data["admin_notes"] == "Fixed this issue"

def test_admin_delete_contact_message(auth_headers):
    # Create a message to delete
    db = TestingSessionLocal()
    new_msg = ContactMessage(
        full_name="Delete Test",
        email="delete.test@example.com",
        subject="Test Delete",
        message="Test Delete Msg"
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    msg_id = new_msg.id
    db.close()

    response = client.delete(
        f"/api/admin/contact-messages/{msg_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Verify deletion
    db = TestingSessionLocal()
    deleted_msg = db.query(ContactMessage).filter(ContactMessage.id == msg_id).first()
    assert deleted_msg is None
    db.close()

def test_admin_export_contact_messages(auth_headers):
    response = client.get("/api/admin/contact-messages/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment; filename=contact_messages.csv" in response.headers["content-disposition"]
    assert "johndoe@example.com" in response.text

