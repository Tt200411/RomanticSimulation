from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    GuestProfile,
    Project,
    RelationshipState,
    SceneArtifact,
    SceneMessage,
    SceneRun,
    SimulationRun,
    StateSnapshot,
)
from app.schemas.project import GuestImportRequest, ProjectCreateRequest
from app.schemas.simulation import SimulationCreateRequest
from app.services.simulation.scene_registry import SCENE_01_CODE


def create_project(db: Session, payload: ProjectCreateRequest) -> Project:
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project_or_404(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def import_guests(db: Session, project: Project, payload: GuestImportRequest) -> list[GuestProfile]:
    guests: list[GuestProfile] = []
    existing_guest_stmt = select(GuestProfile).where(GuestProfile.project_id == project.id)
    for existing_guest in db.scalars(existing_guest_stmt).all():
        db.delete(existing_guest)
    db.flush()

    all_payloads = [("protagonist", payload.protagonist)] + [("guest", guest) for guest in payload.guests]

    for role, item in all_payloads:
        guest = GuestProfile(
            project_id=project.id,
            name=item.name,
            role=role,
            age=item.age,
            city=item.city,
            occupation=item.occupation,
            background_summary=item.background_summary,
            personality_summary=item.personality_summary,
            attachment_style=item.attachment_style,
            appearance_tags=item.appearance_tags,
            personality_tags=item.personality_tags,
            preferred_traits=item.preferred_traits,
            disliked_traits=item.disliked_traits,
            commitment_goal=item.commitment_goal,
            imported_payload=item.model_dump(),
            soul_data=build_soul_data(role, item),
        )
        db.add(guest)
        guests.append(guest)

    db.commit()
    for guest in guests:
        db.refresh(guest)
    return guests


def build_soul_data(role: str, guest_payload) -> dict:
    return {
        "agent_name": guest_payload.name,
        "role": role,
        "stable_profile": {
            "basic_info": {
                "age": guest_payload.age,
                "city": guest_payload.city,
                "job": guest_payload.occupation,
                "appearance_tags": guest_payload.appearance_tags,
            },
            "personality_core": {
                "attachment_style": guest_payload.attachment_style,
                "traits": guest_payload.personality_tags,
            },
            "dating_preferences": {
                "preferred_traits": guest_payload.preferred_traits,
                "disliked_traits": guest_payload.disliked_traits,
                "commitment_goal": guest_payload.commitment_goal,
            },
        },
        "dynamic_state": {
            "current_goal": "find_mutual_and_secure_connection",
            "last_scene_summary": None,
        },
        "relationships": {},
    }


def create_simulation(
    db: Session,
    project: Project,
    payload: SimulationCreateRequest,
) -> tuple[SimulationRun, SceneRun]:
    protagonist = get_protagonist(db, project.id)
    guests = get_target_guests(db, project.id)
    if protagonist is None or not guests:
        raise ValueError("Project must include one protagonist and at least one guest.")

    simulation = SimulationRun(
        project_id=project.id,
        status="queued",
        current_scene_index=1,
        current_scene_code=SCENE_01_CODE,
        strategy_cards=payload.strategy_cards,
    )
    db.add(simulation)
    db.flush()

    scene_run = SceneRun(
        simulation_run_id=simulation.id,
        project_id=project.id,
        scene_index=1,
        scene_code=SCENE_01_CODE,
        status="queued",
    )
    db.add(scene_run)

    for guest in guests:
        metrics = build_initial_relationship_metrics(protagonist, guest)
        relationship = RelationshipState(
            project_id=project.id,
            simulation_run_id=simulation.id,
            protagonist_guest_id=protagonist.id,
            target_guest_id=guest.id,
            metrics=metrics,
            status=derive_relationship_status(metrics),
            recent_trend="observing",
            notes=["初始关系已根据导入资料建立。"],
        )
        db.add(relationship)

    db.commit()
    db.refresh(simulation)
    db.refresh(scene_run)
    return simulation, scene_run


def get_protagonist(db: Session, project_id: str) -> GuestProfile | None:
    stmt = select(GuestProfile).where(
        GuestProfile.project_id == project_id,
        GuestProfile.role == "protagonist",
    )
    return db.scalar(stmt)


def get_target_guests(db: Session, project_id: str) -> list[GuestProfile]:
    stmt = select(GuestProfile).where(
        GuestProfile.project_id == project_id,
        GuestProfile.role == "guest",
    )
    return list(db.scalars(stmt).all())


def get_simulation_or_404(db: Session, simulation_id: str) -> SimulationRun | None:
    return db.get(SimulationRun, simulation_id)


def build_initial_relationship_metrics(protagonist: GuestProfile, guest: GuestProfile) -> dict:
    protagonist_preferences = set(protagonist.preferred_traits or [])
    protagonist_dislikes = set(protagonist.disliked_traits or [])
    guest_tags = set((guest.appearance_tags or []) + (guest.personality_tags or []))
    overlap = len(protagonist_preferences & guest_tags)
    dislikes = len(protagonist_dislikes & guest_tags)

    commitment_alignment = 55 if protagonist.commitment_goal == guest.commitment_goal else 42
    attachment_style = (protagonist.attachment_style or "").lower()
    anxiety_base = 55 if "anxious" in attachment_style else 35
    attraction = clamp(38 + overlap * 9 - dislikes * 7, 20, 82)

    return {
        "initial_attraction": attraction,
        "attraction": clamp(attraction - 3, 20, 80),
        "trust": clamp(26 + overlap * 3, 20, 45),
        "comfort": clamp(34 + overlap * 4 - dislikes * 3, 20, 60),
        "understood": clamp(28 + overlap * 2, 20, 50),
        "expectation": clamp(36 + overlap * 5, 20, 65),
        "disappointment": 8,
        "conflict": 4,
        "anxiety": clamp(anxiety_base - overlap * 3 + dislikes * 2, 20, 65),
        "curiosity": clamp(42 + overlap * 6 - dislikes * 2, 20, 78),
        "exclusivity_pressure": 10,
        "commitment_alignment": commitment_alignment,
    }


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def derive_relationship_status(metrics: dict) -> str:
    attraction = metrics["attraction"]
    trust = metrics["trust"]
    comfort = metrics["comfort"]
    understood = metrics["understood"]
    expectation = metrics["expectation"]
    disappointment = metrics["disappointment"]
    conflict = metrics["conflict"]
    anxiety = metrics["anxiety"]
    curiosity = metrics["curiosity"]
    commitment_alignment = metrics["commitment_alignment"]

    if attraction >= 70 and trust >= 68 and commitment_alignment >= 65 and conflict < 35:
        return "paired"
    if attraction < 25 and trust < 25:
        return "out"
    if disappointment >= 75:
        return "out"
    if trust < 35 and conflict >= 60:
        return "blocked"
    if commitment_alignment < 35:
        return "blocked"
    if attraction < 45 or curiosity < 35:
        if disappointment >= 50:
            return "cooling"
    if attraction >= 60 and (anxiety >= 55 or conflict >= 50):
        return "unstable"
    if (
        attraction >= 65
        and trust >= 60
        and understood >= 55
        and expectation >= 55
        and conflict < 45
    ):
        return "heating_up"
    if attraction >= 50 and comfort >= 50 and trust >= 45 and conflict < 40:
        return "warming"
    return "observing"


def enqueue_scene(scene_run_id: str) -> None:
    from app.core.queue import SCENE_QUEUE_NAME, get_redis_client

    redis_client = get_redis_client()
    redis_client.lpush(SCENE_QUEUE_NAME, scene_run_id)


def claim_scene_by_id(db: Session, scene_run_id: str, claim_timeout_seconds: int) -> SceneRun | None:
    scene_run = db.get(SceneRun, scene_run_id, with_for_update=True)
    if scene_run is None:
        return None

    now = datetime.now(timezone.utc)
    was_failed = scene_run.status == "failed"
    is_stale = (
        scene_run.status in {"claimed", "running"}
        and scene_run.claimed_at is not None
        and scene_run.claimed_at < now - timedelta(seconds=claim_timeout_seconds)
    )
    if scene_run.status not in {"queued", "failed"} and not is_stale:
        return None

    scene_run.status = "claimed"
    scene_run.claim_token = str(uuid4())
    scene_run.claimed_at = now
    scene_run.retry_count = scene_run.retry_count + 1 if is_stale or was_failed else scene_run.retry_count
    db.add(scene_run)
    db.commit()
    db.refresh(scene_run)
    return scene_run


def mark_simulation_running(db: Session, simulation: SimulationRun) -> None:
    simulation.status = "running"
    simulation.started_at = simulation.started_at or datetime.now(timezone.utc)
    db.add(simulation)
    db.commit()


def mark_scene_failed(db: Session, scene_run: SceneRun, simulation: SimulationRun, error_message: str) -> None:
    now = datetime.now(timezone.utc)
    scene_run.status = "failed"
    scene_run.error_message = error_message
    scene_run.finished_at = now
    simulation.status = "failed"
    simulation.error_message = error_message
    simulation.finished_at = now
    error_log = AuditLog(
        simulation_run_id=simulation.id,
        scene_run_id=scene_run.id,
        log_type="error_info",
        payload={"error_message": error_message},
    )
    db.add(scene_run)
    db.add(simulation)
    db.add(error_log)
    db.commit()


def apply_scene_result(
    db: Session,
    scene_run: SceneRun,
    simulation: SimulationRun,
    director_result: dict,
    director_raw_output: dict | str,
    director_input_summary: dict,
) -> None:
    protagonist = get_protagonist(db, simulation.project_id)
    guests = {guest.id: guest for guest in get_target_guests(db, simulation.project_id)}
    relationship_stmt = select(RelationshipState).where(
        RelationshipState.simulation_run_id == simulation.id
    )
    relationships = {item.target_guest_id: item for item in db.scalars(relationship_stmt).all()}

    for delta in director_result["relationship_deltas"]:
        relationship = relationships.get(delta["guest_id"])
        if relationship is None:
            continue
        metrics = dict(relationship.metrics)
        for key, value in delta["changes"].items():
            metrics[key] = clamp(metrics.get(key, 0) + value, 0, 100)
        relationship.metrics = metrics
        relationship.status = derive_relationship_status(metrics)
        relationship.recent_trend = relationship.status
        relationship.notes = [delta["reason"]] + relationship.notes[:3]
        db.add(relationship)

    scene_run.status = "completed"
    scene_run.summary = director_result["scene_summary"]
    scene_run.director_output = director_result
    scene_run.finished_at = datetime.now(timezone.utc)

    simulation.status = "completed"
    simulation.current_scene_index = scene_run.scene_index
    simulation.current_scene_code = scene_run.scene_code
    simulation.latest_scene_summary = director_result["director_summary"]
    simulation.latest_audit_snippet = director_result["next_tension"]
    simulation.finished_at = datetime.now(timezone.utc)

    snapshot_payload = {
        "scene_id": scene_run.scene_code,
        "protagonist": {
            "id": protagonist.id if protagonist else None,
            "name": protagonist.name if protagonist else None,
        },
        "relationships": [
            {
                "guest_id": guest_id,
                "guest_name": guests[guest_id].name,
                "status": relationship.status,
                "recent_trend": relationship.recent_trend,
                "metrics": relationship.metrics,
                "notes": relationship.notes,
            }
            for guest_id, relationship in relationships.items()
            if guest_id in guests
        ],
    }
    snapshot = StateSnapshot(
        simulation_run_id=simulation.id,
        scene_run_id=scene_run.id,
        snapshot=snapshot_payload,
    )
    db.add(snapshot)

    audit_logs = [
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="director_input_summary",
            payload=director_input_summary,
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="director_raw_output",
            payload=director_raw_output
            if isinstance(director_raw_output, dict)
            else {"raw_text": director_raw_output},
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="director_validated_output",
            payload=director_result,
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="guest_agent_outputs",
            payload={
                "guest_directives": director_result["guest_directives"],
                "major_events": director_result["major_events"],
            },
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="applied_state_changes",
            payload={"relationship_deltas": director_result["relationship_deltas"]},
        ),
    ]
    for item in audit_logs:
        db.add(item)

    db.add(scene_run)
    db.add(simulation)
    db.commit()


def get_latest_snapshot(db: Session, simulation_id: str) -> StateSnapshot | None:
    stmt = (
        select(StateSnapshot)
        .where(StateSnapshot.simulation_run_id == simulation_id)
        .order_by(StateSnapshot.created_at.desc())
    )
    return db.scalar(stmt)


def get_recent_audit_logs(db: Session, simulation_id: str) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.simulation_run_id == simulation_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    )
    return list(db.scalars(stmt).all())


def get_scene_messages(db: Session, scene_run_id: str) -> list[SceneMessage]:
    stmt = (
        select(SceneMessage)
        .where(SceneMessage.scene_run_id == scene_run_id)
        .order_by(SceneMessage.turn_index.asc(), SceneMessage.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def get_scene_artifact(
    db: Session,
    scene_run_id: str,
    artifact_type: str,
) -> SceneArtifact | None:
    stmt = select(SceneArtifact).where(
        SceneArtifact.scene_run_id == scene_run_id,
        SceneArtifact.artifact_type == artifact_type,
    )
    return db.scalar(stmt)


def get_scene_artifacts(db: Session, simulation_id: str) -> list[SceneArtifact]:
    stmt = select(SceneArtifact).where(SceneArtifact.simulation_run_id == simulation_id)
    return list(db.scalars(stmt).all())


def build_relationship_surface_metrics(metrics: dict) -> dict[str, int]:
    keys = [
        "initial_attraction",
        "comfort",
        "trust",
        "curiosity",
        "anxiety",
    ]
    return {key: int(metrics.get(key, 0)) for key in keys}
