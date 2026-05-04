from fastapi import APIRouter, Depends

from apps.api.schemas.users import UserIdentity
from apps.api.services.user_context import current_user_id


router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserIdentity)
def get_current_user(user_id: str = Depends(current_user_id)) -> UserIdentity:
    return UserIdentity(user_id=user_id)
