from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import verify_cognito_token
from backend.app.db.models.user import User
from backend.app.db.session import get_db

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates the Cognito Bearer token and returns the corresponding User.
    If the user does not exist in the local database, it provisions the user record automatically.
    """
    token = credentials.credentials if credentials else None
    claims = verify_cognito_token(token)

    cognito_sub = claims.get("sub")
    email = claims.get("email", f"{cognito_sub}@example.com")
    full_name = claims.get("name")

    stmt = select(User).where(User.cognito_sub == cognito_sub)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision user on first authenticated request
        user = User(
            cognito_sub=cognito_sub,
            email=email,
            full_name=full_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user
