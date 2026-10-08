from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    thread_id: str
    status: str
    message: str
    data: dict[str, Any] | None = None


class ResumeRequest(BaseModel):
    approval: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    restaurant_id: str
    date: str
    time: str
    party_size: int
    status: str