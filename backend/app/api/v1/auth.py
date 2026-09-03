from pydantic import BaseModel
from fastapi import APIRouter, Depends
from backend.app.api.deps import get_current_user
from backend.app.db.models.user import User

router = APIRouter(tags=["Auth"])


class UserProfileResponse(BaseModel):
    id: str
    email: str
    cognito_sub: str
    full_name: str | None


@router.get("/auth/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Returns the current authenticated user's profile info."""
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        cognito_sub=current_user.cognito_sub,
        full_name=current_user.full_name,
    )
