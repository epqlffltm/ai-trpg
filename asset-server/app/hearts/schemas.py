# asset-server/app/hearts/schemas.py

"""관심(하트, #989)의 응답 모양. trpg-server 의 것과 같다."""

from pydantic import BaseModel


class HeartState(BaseModel):
    """내가 관심을 두었는지와 관심의 수. 두고 거둔 뒤의 값이다."""

    hearted: bool
    heart_count: int
