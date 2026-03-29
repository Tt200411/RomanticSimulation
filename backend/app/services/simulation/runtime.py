from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AgentTurn,
    AuditLog,
    GuestProfile,
    RelationshipState,
    SceneArtifact,
    SceneMessage,
    SceneRun,
    SimulationRun,
    StateSnapshot,
)
from app.schemas.runtime import SceneRuntimeExecution
from app.services.director.scene_01_intro import (
    build_agent_input,
    build_input_summary,
    build_scene_01_context,
    finalize_scene_01_intro,
    generate_agent_turn,
    plan_scene_01_intro,
)
from app.services.simulation.service import (
    clamp,
    derive_relationship_status,
    get_protagonist,
    get_target_guests,
)


def execute_scene_01_intro_runtime(
    db: Session,
    scene_run: SceneRun,
    simulation: SimulationRun,
) -> SceneRuntimeExecution:
    if scene_run.retry_count > 0:
        reset_scene_runtime_records(db, scene_run.id)

    context = build_scene_01_context(db, simulation)
    input_summary = build_input_summary(context)
    plan, plan_raw = plan_scene_01_intro(context)
    replace_scene_artifact(
        db,
        simulation.id,
        scene_run.id,
        "director_plan",
        plan.model_dump(),
        commit=True,
    )
    persist_director_plan_audit_logs(
        db,
        simulation.id,
        scene_run.id,
        input_summary,
        plan_raw,
        plan.model_dump(),
    )

    transcript = []
    for turn_index, speaker_guest_id in enumerate(plan.turn_order, start=1):
        started_at = datetime.now(timezone.utc)
        input_payload = build_agent_input(context, plan, transcript, turn_index, speaker_guest_id)
        try:
            turn, raw_output, normalized_input = generate_agent_turn(
                context,
                plan,
                transcript,
                turn_index,
                speaker_guest_id,
            )
        except Exception as exc:  # noqa: BLE001
            db.add(
                AgentTurn(
                    simulation_run_id=simulation.id,
                    scene_run_id=scene_run.id,
                    turn_index=turn_index,
                    guest_id=speaker_guest_id,
                    agent_name=context["participant_lookup"][speaker_guest_id]["name"],
                    status="failed",
                    input_payload=input_payload,
                    error_message=str(exc),
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
            raise

        transcript.append(turn)
        db.add(
            AgentTurn(
                simulation_run_id=simulation.id,
                scene_run_id=scene_run.id,
                turn_index=turn.turn_index,
                guest_id=turn.speaker_guest_id,
                agent_name=turn.speaker_name,
                status="completed",
                input_payload=normalized_input,
                raw_output=raw_output if isinstance(raw_output, dict) else {"raw_text": raw_output},
                normalized_output=turn.model_dump(),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            SceneMessage(
                simulation_run_id=simulation.id,
                scene_run_id=scene_run.id,
                turn_index=turn.turn_index,
                speaker_guest_id=turn.speaker_guest_id,
                speaker_name=turn.speaker_name,
                message_role="agent",
                utterance=turn.utterance,
                behavior_summary=turn.behavior_summary,
                intent_tags=turn.intent_tags,
                target_guest_ids=turn.target_guest_ids,
                visible_context_summary=input_payload["visible_context"],
                raw_output=raw_output if isinstance(raw_output, dict) else {"raw_text": raw_output},
            )
        )
        db.commit()

    referee_result, referee_raw = finalize_scene_01_intro(context, plan, transcript)
    replay_payload = {
        "simulation_id": simulation.id,
        "scene_run_id": scene_run.id,
        "scene_code": scene_run.scene_code,
        "scene_index": scene_run.scene_index,
        "status": "completed",
        "summary": referee_result.scene_summary,
        "scene_plan": plan.model_dump(),
        "messages": [message.model_dump() for message in transcript],
        "major_events": [event.model_dump() for event in referee_result.major_events],
        "relationship_deltas": [
            relationship_delta.model_dump() for relationship_delta in referee_result.relationship_deltas
        ],
        "next_tension": referee_result.next_tension,
        "replay_url": f"/simulations/{simulation.id}/scenes/{scene_run.id}",
    }
    return SceneRuntimeExecution(
        input_summary=input_summary,
        director_plan=plan,
        director_plan_raw=plan_raw,
        messages=transcript,
        referee_result=referee_result,
        referee_raw=referee_raw,
        replay_payload=replay_payload,
    )


def apply_scene_runtime_result(
    db: Session,
    scene_run: SceneRun,
    simulation: SimulationRun,
    execution: SceneRuntimeExecution,
) -> None:
    protagonist = get_protagonist(db, simulation.project_id)
    guests = {guest.id: guest for guest in get_target_guests(db, simulation.project_id)}
    relationship_stmt = select(RelationshipState).where(
        RelationshipState.simulation_run_id == simulation.id
    )
    relationships = {item.target_guest_id: item for item in db.scalars(relationship_stmt).all()}

    for delta in execution.referee_result.relationship_deltas:
        relationship = relationships.get(delta.guest_id)
        if relationship is None:
            continue
        metrics = dict(relationship.metrics)
        for key, value in delta.changes.items():
            metrics[key] = clamp(metrics.get(key, 0) + value, 0, 100)
        relationship.metrics = metrics
        relationship.status = derive_relationship_status(metrics)
        relationship.recent_trend = derive_recent_trend(delta.changes)
        relationship.notes = [delta.reason] + relationship.notes[:3]
        db.add(relationship)

    scene_run.status = "completed"
    scene_run.summary = execution.referee_result.scene_summary
    scene_run.director_output = {
        "director_plan": execution.director_plan.model_dump(),
        "scene_referee_result": execution.referee_result.model_dump(),
    }
    scene_run.finished_at = datetime.now(timezone.utc)

    simulation.status = "completed"
    simulation.current_scene_index = scene_run.scene_index
    simulation.current_scene_code = scene_run.scene_code
    simulation.latest_scene_summary = execution.referee_result.scene_summary
    simulation.latest_audit_snippet = execution.referee_result.next_tension
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
    db.add(
        StateSnapshot(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            snapshot=snapshot_payload,
        )
    )

    replace_scene_artifact(
        db,
        simulation.id,
        scene_run.id,
        "scene_referee_result",
        execution.referee_result.model_dump(),
        commit=False,
    )
    replace_scene_artifact(
        db,
        simulation.id,
        scene_run.id,
        "scene_replay_dto",
        execution.replay_payload,
        commit=False,
    )

    audit_logs = [
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="guest_agent_outputs",
            payload={"messages": [message.model_dump() for message in execution.messages]},
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="scene_referee_result",
            payload=execution.referee_result.model_dump(),
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="scene_referee_raw_output",
            payload=execution.referee_raw
            if isinstance(execution.referee_raw, dict)
            else {"raw_text": execution.referee_raw},
        ),
        AuditLog(
            simulation_run_id=simulation.id,
            scene_run_id=scene_run.id,
            log_type="applied_state_changes",
            payload={"relationship_deltas": execution.referee_result.model_dump()["relationship_deltas"]},
        ),
    ]
    for item in audit_logs:
        db.add(item)

    db.add(scene_run)
    db.add(simulation)
    db.commit()


def reset_scene_runtime_records(db: Session, scene_run_id: str) -> None:
    db.execute(delete(SceneMessage).where(SceneMessage.scene_run_id == scene_run_id))
    db.execute(delete(AgentTurn).where(AgentTurn.scene_run_id == scene_run_id))
    db.execute(delete(SceneArtifact).where(SceneArtifact.scene_run_id == scene_run_id))
    db.commit()


def replace_scene_artifact(
    db: Session,
    simulation_run_id: str,
    scene_run_id: str,
    artifact_type: str,
    payload: dict,
    *,
    commit: bool,
) -> None:
    existing = db.scalar(
        select(SceneArtifact).where(
            SceneArtifact.scene_run_id == scene_run_id,
            SceneArtifact.artifact_type == artifact_type,
        )
    )
    if existing is None:
        existing = SceneArtifact(
            simulation_run_id=simulation_run_id,
            scene_run_id=scene_run_id,
            artifact_type=artifact_type,
            payload=payload,
        )
    else:
        existing.payload = payload
    db.add(existing)
    if commit:
        db.commit()


def persist_director_plan_audit_logs(
    db: Session,
    simulation_run_id: str,
    scene_run_id: str,
    input_summary: dict,
    director_plan_raw: dict | str,
    director_plan_validated: dict,
) -> None:
    db.add(
        AuditLog(
            simulation_run_id=simulation_run_id,
            scene_run_id=scene_run_id,
            log_type="director_input_summary",
            payload=input_summary,
        )
    )
    db.add(
        AuditLog(
            simulation_run_id=simulation_run_id,
            scene_run_id=scene_run_id,
            log_type="director_plan_raw_output",
            payload=director_plan_raw
            if isinstance(director_plan_raw, dict)
            else {"raw_text": director_plan_raw},
        )
    )
    db.add(
        AuditLog(
            simulation_run_id=simulation_run_id,
            scene_run_id=scene_run_id,
            log_type="director_plan_validated",
            payload=director_plan_validated,
        )
    )
    db.commit()


def derive_recent_trend(changes: dict[str, int]) -> str:
    score = 0
    for key, value in changes.items():
        if key in {"initial_attraction", "attraction", "comfort", "trust", "curiosity", "expectation"}:
            score += value
        elif key in {"anxiety", "disappointment", "conflict"}:
            score -= value
    if score >= 8:
        return "warming"
    if score <= -8:
        return "cooling"
    return "observing"
