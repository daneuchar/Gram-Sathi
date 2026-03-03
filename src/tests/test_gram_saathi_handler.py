import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.handlers.gram_saathi import GramSaathiHandler


def test_handler_init_defaults():
    h = GramSaathiHandler()
    assert h.phone is None
    assert h.is_onboarding is False
    assert h.farmer_profile is None
    assert h.conversation_history == []


def test_copy_returns_fresh_handler():
    h = GramSaathiHandler()
    h.phone = "+919876543210"
    h2 = h.copy()
    # copy() for a new connection should NOT carry over state
    assert h2.phone is None
    assert h2.is_onboarding is False
    assert h2.farmer_profile is None


def test_is_new_user_true_when_name_none():
    from app.models.user import User
    user = User(phone="+919876543210", name=None)
    h = GramSaathiHandler()
    assert h._is_new_user(user) is True


def test_is_new_user_false_when_name_set():
    from app.models.user import User
    user = User(phone="+919876543210", name="Ramesh")
    h = GramSaathiHandler()
    assert h._is_new_user(user) is False
