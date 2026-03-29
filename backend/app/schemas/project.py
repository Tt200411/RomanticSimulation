from datetime import datetime

from pydantic import BaseModel, Field


class GuestImportPayload(BaseModel):
    name: str
    age: int | None = None
    city: str | None = None
    occupation: str | None = None
    background_summary: str | None = None
    personality_summary: str | None = None
    attachment_style: str | None = None
    appearance_tags: list[str] = Field(default_factory=list)
    personality_tags: list[str] = Field(default_factory=list)
    preferred_traits: list[str] = Field(default_factory=list)
    disliked_traits: list[str] = Field(default_factory=list)
    commitment_goal: str | None = "serious_relationship"


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class GuestImportRequest(BaseModel):
    protagonist: GuestImportPayload
    guests: list[GuestImportPayload]


class GuestSummary(BaseModel):
    id: str
    name: str
    role: str
    city: str | None = None
    occupation: str | None = None
    attachment_style: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    guest_count: int
    created_at: datetime


class ProjectDetailResponse(ProjectResponse):
    guests: list[GuestSummary]

