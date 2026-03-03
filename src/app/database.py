from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.models.base import Base

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


from app.models.user import User


async def get_or_create_user(phone: str) -> User:
    """Load user by phone, creating a minimal record if not found."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, phone)
        if user is None:
            user = User(phone=phone)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def update_user_profile(
    phone: str,
    *,
    name: str | None = None,
    state: str | None = None,
    district: str | None = None,
    language: str | None = None,
) -> None:
    """Update farmer profile fields. Only sets fields that are provided."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, phone)
        if user is None:
            return
        if name is not None:
            user.name = name
        if state is not None:
            user.state = state
        if district is not None:
            user.district = district
        if language is not None:
            user.language = language
        await session.commit()
