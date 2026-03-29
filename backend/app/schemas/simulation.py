from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.director import DirectorSceneResult


class SimulationCreateRequest(BaseModel):
    strategy_cards: list[str] = Field(default_factory=list)


class SceneRunSummary(BaseModel):
    id: str
    scene_code: str
    scene_index: int
    status: str
    retry_count: int
    summary: str | None = None
    error_message: str | None = None
    finished_at: datetime | None = None


class RelationshipStateView(BaseModel):
    guest_id: str
    guest_name: str
    status: str
    recent_trend: str
    metrics: dict
    notes: list[str]


class AuditLogView(BaseModel):
    log_type: str
    payload: dict
    created_at: datetime


class SimulationResponse(BaseModel):
    id: str
    project_id: str
    status: str
    current_scene_index: int
    current_scene_code: str | None = None
    latest_scene_summary: str | None = None
    latest_audit_snippet: str | None = None
    created_at: datetime


class SimulationDetailResponse(SimulationResponse):
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    strategy_cards: list[str]
    scenes: list[SceneRunSummary]
    director_output: DirectorSceneResult | None = None
    relationships: list[RelationshipStateView]
    latest_snapshot: dict | None = None
    recent_audit_logs: list[AuditLogView]
