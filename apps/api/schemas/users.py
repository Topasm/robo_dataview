from pydantic import BaseModel


class UserIdentity(BaseModel):
    user_id: str
