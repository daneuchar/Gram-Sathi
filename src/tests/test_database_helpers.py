import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.database import get_or_create_user, update_user_profile


@pytest.mark.asyncio
async def test_get_or_create_user_new():
    mock_session = AsyncMock()
    mock_session.get.return_value = None  # user not found
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        user = await get_or_create_user("+919876543210")

    mock_session.add.assert_called_once()
    added = mock_session.add.call_args[0][0]
    assert added.phone == "+919876543210"
    assert added.name is None


@pytest.mark.asyncio
async def test_get_or_create_user_existing():
    from app.models.user import User
    existing = User(phone="+919876543210", name="Ramesh", state="Tamil Nadu")
    mock_session = AsyncMock()
    mock_session.get.return_value = existing

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        user = await get_or_create_user("+919876543210")

    mock_session.add.assert_not_called()
    assert user.name == "Ramesh"


@pytest.mark.asyncio
async def test_update_user_profile():
    from app.models.user import User
    existing = User(phone="+919876543210")
    mock_session = AsyncMock()
    mock_session.get.return_value = existing
    mock_session.commit = AsyncMock()

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await update_user_profile("+919876543210", name="Ramesh", state="Tamil Nadu", district="Coimbatore", language="ta-IN")

    assert existing.name == "Ramesh"
    assert existing.state == "Tamil Nadu"
    assert existing.district == "Coimbatore"
    assert existing.language == "ta-IN"
    mock_session.commit.assert_called_once()
