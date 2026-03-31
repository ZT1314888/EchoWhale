from pydantic import BaseModel


class CoachState(BaseModel):
    turn_count: int = 0
