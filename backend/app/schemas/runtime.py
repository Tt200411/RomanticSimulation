from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.director import ALLOWED_METRICS


class DirectorPlanParticipant(BaseModel):
    guest_id: str
    name: str
    role: str


class DirectorPlanDirective(BaseModel):
    guest_id: str
    directive: str


class DirectorPlan(BaseModel):
    scene_id: str
    scene_goal: str
    scene_frame: str
    participants: list[DirectorPlanParticipant]
    turn_order: list[str]
    agent_directives: list[DirectorPlanDirective] = Field(default_factory=list)
    evaluation_focus: list[str] = Field(default_factory=list)
    stop_condition: str
    active_tension: str


class AgentTurnPayload(BaseModel):
    speaker_guest_id: str
    speaker_name: str
    turn_index: int
    utterance: str
    behavior_summary: str
    intent_tags: list[str] = Field(default_factory=list)
    target_guest_ids: list[str] = Field(default_factory=list)
    self_observation: str | None = None


class SceneEvent(BaseModel):
    title: str
    description: str | None = None
    event_tags: list[str] = Field(default_factory=list)
    target_guest_ids: list[str] = Field(default_factory=list)


class SceneRelationshipDelta(BaseModel):
    guest_id: str
    changes: dict[str, int]
    reason: str

    @field_validator("changes")
    @classmethod
    def validate_changes(cls, value: dict[str, int]) -> dict[str, int]:
        invalid_keys = [key for key in value if key not in ALLOWED_METRICS]
        if invalid_keys:
            raise ValueError(f"Invalid metric keys: {', '.join(invalid_keys)}")
        invalid_values = [delta for delta in value.values() if delta < -18 or delta > 18]
        if invalid_values:
            raise ValueError("Every metric delta must stay within [-18, 18]")
        return value


class SceneRefereeResult(BaseModel):
    scene_id: str
    scene_summary: str
    major_events: list[SceneEvent] = Field(default_factory=list)
    relationship_deltas: list[SceneRelationshipDelta] = Field(default_factory=list)
    next_tension: str


class SceneRuntimeExecution(BaseModel):
    input_summary: dict
    director_plan: DirectorPlan
    director_plan_raw: dict | str
    messages: list[AgentTurnPayload] = Field(default_factory=list)
    referee_result: SceneRefereeResult
    referee_raw: dict | str
    replay_payload: dict


class TimelineScenePreview(BaseModel):
    scene_run_id: str
    scene_code: str
    scene_index: int
    status: str
    summary: str | None = None
    tension: str | None = None
    replay_url: str | None = None


class RelationshipCard(BaseModel):
    guest_id: str
    guest_name: str
    status: str
    trend: str
    top_reasons: list[str] = Field(default_factory=list)
    surface_metrics: dict[str, int] = Field(default_factory=dict)


class SimulationOverviewResponse(BaseModel):
    id: str
    project_id: str
    status: str
    current_scene_index: int
    current_scene_code: str | None = None
    latest_scene_summary: str | None = None
    latest_audit_snippet: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    strategy_cards: list[str] = Field(default_factory=list)
    active_tension: str | None = None
    latest_scene_replay_url: str | None = None
    scene_timeline_preview: list[TimelineScenePreview] = Field(default_factory=list)
    relationship_cards: list[RelationshipCard] = Field(default_factory=list)
    recent_audit_logs: list[dict] = Field(default_factory=list)


class SceneReplayResponse(BaseModel):
    simulation_id: str
    scene_run_id: str
    scene_code: str
    scene_index: int
    status: str
    summary: str | None = None
    scene_plan: DirectorPlan | None = None
    messages: list[AgentTurnPayload] = Field(default_factory=list)
    major_events: list[SceneEvent] = Field(default_factory=list)
    relationship_deltas: list[SceneRelationshipDelta] = Field(default_factory=list)
    next_tension: str | None = None
    replay_url: str | None = None


class SimulationTimelineResponse(BaseModel):
    simulation_id: str
    scenes: list[TimelineScenePreview] = Field(default_factory=list)


class SimulationRelationshipsResponse(BaseModel):
    simulation_id: str
    relationships: list[RelationshipCard] = Field(default_factory=list)
