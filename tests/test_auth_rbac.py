import pytest
from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.core.security import hash_password, verify_password
from app.db.models.identity import AdminAccount, User
from app.api.v1.internal_bot import verify_bot_actor

def test_password_hashing():
    pw = "SuperSecret2026!"
    hashed = hash_password(pw)
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(pw, hashed)
    assert not verify_password("WrongPassword", hashed)

@pytest.mark.asyncio
async def test_bot_delegation_security(db_session):
    # 1. Invalid Bot API Key -> Fails with UNAUTHORIZED
    with pytest.raises(BoconicException) as exc_key:
        await verify_bot_actor(
            x_bot_api_key="WRONG_KEY",
            x_telegram_user_id=999999,
            db=db_session,
        )
    assert exc_key.value.code == ErrorCode.UNAUTHORIZED

    # 2. Valid Bot Key with Telegram User ID -> Auto-syncs and returns User actor
    actor = await verify_bot_actor(
        x_bot_api_key=settings.BOT_API_KEY,
        x_telegram_user_id=888888,
        db=db_session,
    )
    assert actor.id is not None
    assert actor.telegram_user_id == 888888
    assert actor.public_alias.startswith("User #")

    # 3. Banned actor -> Fails with FORBIDDEN
    actor.status = "banned"
    await db_session.flush()

    with pytest.raises(BoconicException) as exc_ban:
        await verify_bot_actor(
            x_bot_api_key=settings.BOT_API_KEY,
            x_telegram_user_id=888888,
            db=db_session,
        )
    assert exc_ban.value.code == ErrorCode.FORBIDDEN
