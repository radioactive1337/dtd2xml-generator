"""Tests for Git author identity resolution."""

from app.services.git_identity_service import _pick_gitlab_email


def test_pick_gitlab_email_prefers_commit_email():
    data = {
        "name": "Alice",
        "commit_email": "alice@company.com",
        "email": "hidden@company.com",
    }
    assert _pick_gitlab_email(data) == "alice@company.com"


def test_pick_gitlab_email_builds_noreply_fallback():
    data = {"id": 42, "username": "alice", "name": "Alice"}
    assert _pick_gitlab_email(data) == "42+alice@users.noreply.gitlab.com"
