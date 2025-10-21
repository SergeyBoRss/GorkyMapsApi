from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Location(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class RouteRequest(BaseModel):
    interests: List[str] = Field(..., min_items=1)
    user_location: Optional[Location] = None
    walking_time: float = Field(..., gt=0)

    @field_validator("interests", mode="before")
    @classmethod
    def strip_interests(cls, interests: List[str]) -> List[str]:
        if not isinstance(interests, list):
            raise TypeError("interests must be a list of strings")
        cleaned = [str(interest).strip() for interest in interests if str(interest).strip()]
        if not cleaned:
            raise ValueError("At least one non-empty interest is required")
        return cleaned


class RoutePoint(BaseModel):
    latitude: float
    longitude: float
    title: str
    description: str


class RouteResponse(BaseModel):
    routes: List[List[RoutePoint]]
