from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import GuestProfile, RelationshipState, SceneRun, SimulationRun
from app.schemas.runtime import (
    AgentTurnPayload,
    DirectorPlan,
    RelationshipCard,
    SceneReplayResponse,
    SceneRefereeResult,
    SimulationOverviewResponse,
    SimulationRelationshipsResponse,
    SimulationTimelineResponse,
    TimelineScenePreview,
)
from app.schemas.simulation import SimulationCreateRequest, SimulationResponse
from app.services.simulation.service import (
    build_relationship_surface_metrics,
    create_simulation,
    enqueue_scene,
    get_project_or_404,
    get_recent_audit_logs,
    get_scene_artifact,
    get_scene_artifacts,
    get_scene_messages,
    get_simulation_or_404,
)

router = APIRouter(tags=["simulations"])


@router.post(
    "/projects/{project_id}/simulations",
    response_model=SimulationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_simulation_endpoint(
    project_id: str,
    payload: SimulationCreateRequest,
    db: Session = Depends(get_db),
) -> SimulationResponse:
    project = get_project_or_404(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        simulation, scene_run = create_simulation(db, project, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    enqueue_scene(scene_run.id)
    return serialize_simulation(simulation)


@router.get("/simulations/{simulation_id}", response_model=SimulationOverviewResponse)
def get_simulation_endpoint(
    simulation_id: str,
    db: Session = Depends(get_db),
) -> SimulationOverviewResponse:
    simulation = get_simulation_or_404(db, simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")

    scenes = list(
        db.scalars(
            select(SceneRun)
            .where(SceneRun.simulation_run_id == simulation.id)
            .order_by(SceneRun.scene_index.asc())
        ).all()
    )
    relationships = list(
        db.scalars(
            select(RelationshipState).where(RelationshipState.simulation_run_id == simulation.id)
        ).all()
    )
    guests = {
        guest.id: guest
        for guest in db.scalars(
            select(GuestProfile).where(GuestProfile.project_id == simulation.project_id)
        ).all()
    }
    artifacts = get_scene_artifacts(db, simulation.id)
    artifact_lookup = {(item.scene_run_id, item.artifact_type): item.payload for item in artifacts}

    timeline_preview = [
        build_timeline_preview(simulation.id, scene, artifact_lookup)
        for scene in scenes
    ]
    relationship_cards = build_relationship_cards(relationships, guests)
    latest_scene = scenes[-1] if scenes else None
    latest_scene_replay_url = (
        f"/simulations/{simulation.id}/scenes/{latest_scene.id}" if latest_scene else None
    )
    active_tension = None
    if latest_scene:
        replay_payload = artifact_lookup.get((latest_scene.id, "scene_replay_dto"))
        referee_payload = artifact_lookup.get((latest_scene.id, "scene_referee_result"))
        if replay_payload:
            active_tension = replay_payload.get("next_tension")
        elif referee_payload:
            active_tension = referee_payload.get("next_tension")

    audit_logs = get_recent_audit_logs(db, simulation.id)
    return SimulationOverviewResponse(
        id=simulation.id,
        project_id=simulation.project_id,
        status=simulation.status,
        current_scene_index=simulation.current_scene_index,
        current_scene_code=simulation.current_scene_code,
        latest_scene_summary=simulation.latest_scene_summary,
        latest_audit_snippet=simulation.latest_audit_snippet,
        created_at=simulation.created_at,
        started_at=simulation.started_at,
        finished_at=simulation.finished_at,
        error_message=simulation.error_message,
        strategy_cards=simulation.strategy_cards,
        active_tension=active_tension or simulation.latest_audit_snippet,
        latest_scene_replay_url=latest_scene_replay_url,
        scene_timeline_preview=timeline_preview,
        relationship_cards=relationship_cards,
        recent_audit_logs=[
            {
                "log_type": item.log_type,
                "payload": item.payload,
                "created_at": item.created_at.isoformat(),
            }
            for item in audit_logs
        ],
    )


@router.get(
    "/simulations/{simulation_id}/scenes/{scene_run_id}",
    response_model=SceneReplayResponse,
)
def get_scene_replay_endpoint(
    simulation_id: str,
    scene_run_id: str,
    db: Session = Depends(get_db),
) -> SceneReplayResponse:
    simulation = get_simulation_or_404(db, simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")

    scene_run = db.scalar(
        select(SceneRun).where(
            SceneRun.id == scene_run_id,
            SceneRun.simulation_run_id == simulation.id,
        )
    )
    if scene_run is None:
        raise HTTPException(status_code=404, detail="Scene not found.")

    replay_artifact = get_scene_artifact(db, scene_run.id, "scene_replay_dto")
    if replay_artifact is not None:
        return SceneReplayResponse.model_validate(replay_artifact.payload)

    plan_artifact = get_scene_artifact(db, scene_run.id, "director_plan")
    referee_artifact = get_scene_artifact(db, scene_run.id, "scene_referee_result")
    messages = [
        AgentTurnPayload(
            speaker_guest_id=item.speaker_guest_id,
            speaker_name=item.speaker_name,
            turn_index=item.turn_index,
            utterance=item.utterance,
            behavior_summary=item.behavior_summary or "",
            intent_tags=item.intent_tags,
            target_guest_ids=item.target_guest_ids,
            self_observation=None,
        )
        for item in get_scene_messages(db, scene_run.id)
    ]
    referee = (
        SceneRefereeResult.model_validate(referee_artifact.payload)
        if referee_artifact is not None
        else None
    )
    return SceneReplayResponse(
        simulation_id=simulation.id,
        scene_run_id=scene_run.id,
        scene_code=scene_run.scene_code,
        scene_index=scene_run.scene_index,
        status=scene_run.status,
        summary=scene_run.summary,
        scene_plan=DirectorPlan.model_validate(plan_artifact.payload) if plan_artifact else None,
        messages=messages,
        major_events=referee.major_events if referee else [],
        relationship_deltas=referee.relationship_deltas if referee else [],
        next_tension=referee.next_tension if referee else None,
        replay_url=f"/simulations/{simulation.id}/scenes/{scene_run.id}",
    )


@router.get(
    "/simulations/{simulation_id}/timeline",
    response_model=SimulationTimelineResponse,
)
def get_simulation_timeline_endpoint(
    simulation_id: str,
    db: Session = Depends(get_db),
) -> SimulationTimelineResponse:
    simulation = get_simulation_or_404(db, simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")

    scenes = list(
        db.scalars(
            select(SceneRun)
            .where(SceneRun.simulation_run_id == simulation.id)
            .order_by(SceneRun.scene_index.asc())
        ).all()
    )
    artifacts = get_scene_artifacts(db, simulation.id)
    artifact_lookup = {(item.scene_run_id, item.artifact_type): item.payload for item in artifacts}
    return SimulationTimelineResponse(
        simulation_id=simulation.id,
        scenes=[
            build_timeline_preview(simulation.id, scene, artifact_lookup)
            for scene in scenes
        ],
    )


@router.get(
    "/simulations/{simulation_id}/relationships",
    response_model=SimulationRelationshipsResponse,
)
def get_simulation_relationships_endpoint(
    simulation_id: str,
    db: Session = Depends(get_db),
) -> SimulationRelationshipsResponse:
    simulation = get_simulation_or_404(db, simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")

    relationships = list(
        db.scalars(
            select(RelationshipState).where(RelationshipState.simulation_run_id == simulation.id)
        ).all()
    )
    guests = {
        guest.id: guest
        for guest in db.scalars(
            select(GuestProfile).where(GuestProfile.project_id == simulation.project_id)
        ).all()
    }
    return SimulationRelationshipsResponse(
        simulation_id=simulation.id,
        relationships=build_relationship_cards(relationships, guests),
    )


def build_timeline_preview(
    simulation_id: str,
    scene: SceneRun,
    artifact_lookup: dict[tuple[str, str], dict],
) -> TimelineScenePreview:
    replay_payload = artifact_lookup.get((scene.id, "scene_replay_dto"))
    referee_payload = artifact_lookup.get((scene.id, "scene_referee_result"))
    tension = None
    summary = scene.summary
    if replay_payload:
        summary = replay_payload.get("summary") or summary
        tension = replay_payload.get("next_tension")
    elif referee_payload:
        summary = referee_payload.get("scene_summary") or summary
        tension = referee_payload.get("next_tension")

    return TimelineScenePreview(
        scene_run_id=scene.id,
        scene_code=scene.scene_code,
        scene_index=scene.scene_index,
        status=scene.status,
        summary=summary,
        tension=tension,
        replay_url=f"/simulations/{simulation_id}/scenes/{scene.id}",
    )


def build_relationship_cards(
    relationships: list[RelationshipState],
    guests: dict[str, GuestProfile],
) -> list[RelationshipCard]:
    cards = []
    for item in relationships:
        guest = guests.get(item.target_guest_id)
        if guest is None:
            continue
        cards.append(
            RelationshipCard(
                guest_id=item.target_guest_id,
                guest_name=guest.name,
                status=item.status,
                trend=item.recent_trend,
                top_reasons=item.notes[:3],
                surface_metrics=build_relationship_surface_metrics(item.metrics),
            )
        )
    cards.sort(
        key=lambda item: (
            item.surface_metrics.get("initial_attraction", 0)
            + item.surface_metrics.get("comfort", 0)
            + item.surface_metrics.get("trust", 0)
        ),
        reverse=True,
    )
    return cards


def serialize_simulation(simulation: SimulationRun) -> SimulationResponse:
    return SimulationResponse(
        id=simulation.id,
        project_id=simulation.project_id,
        status=simulation.status,
        current_scene_index=simulation.current_scene_index,
        current_scene_code=simulation.current_scene_code,
        latest_scene_summary=simulation.latest_scene_summary,
        latest_audit_snippet=simulation.latest_audit_snippet,
        created_at=simulation.created_at,
    )
