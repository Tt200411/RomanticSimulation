from __future__ import annotations

import json
import re
from collections.abc import Iterable

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import GuestProfile, RelationshipState, SimulationRun
from app.schemas.runtime import (
    AgentTurnPayload,
    DirectorPlan,
    SceneEvent,
    SceneRefereeResult,
    SceneRelationshipDelta,
)

PLAN_SYSTEM_PROMPT = """
你是恋爱模拟器 Phase 2 的 Director Planner。
你只负责 scene_01_intro 的编排，不替角色发言。
你必须只返回一个 JSON 对象，不要输出任何解释、markdown、代码块。

硬性规则：
1. scene_id 固定为 scene_01_intro。
2. turn_order 必须先让 protagonist 发言，再让 2-3 位 guest 依次回应。
3. agent_directives 只给每个 guest 一句可执行的表演 directive。
4. active_tension 必须围绕“第一印象是否能转成后续交流意愿”。
5. stop_condition 只能描述何时可以结束初见场景，不允许进入下一场剧情。
""".strip()

AGENT_SYSTEM_PROMPT = """
你是恋爱模拟器中的单个角色 Agent。
你只能扮演当前 speaker，不能代替其他角色，也不能决定最终关系结果。
你必须只返回一个 JSON 对象，不要输出任何解释、markdown、代码块。

硬性规则：
1. utterance 只写当前 speaker 会说的话，不超过 2 句。
2. behavior_summary 用一句话概括说话方式或行为氛围。
3. intent_tags 只写 1-3 个简短标签，例如 build_comfort、signal_interest、test_chemistry。
4. target_guest_ids 只能写当前 speaker 这轮主要指向的人。
5. self_observation 只能是当前 speaker 的主观感受，不允许偷看别人的隐藏想法。
""".strip()

FINALIZE_SYSTEM_PROMPT = """
你是恋爱模拟器 Phase 2 的 Scene Referee。
你只能根据 transcript 做结构化裁决，不能创造与 transcript 无关的新剧情。
你必须只返回一个 JSON 对象，不要输出任何解释、markdown、代码块。

硬性规则：
1. scene_id 固定为 scene_01_intro。
2. relationship_deltas 只允许小幅变化，单个字段范围 -18 到 18。
3. 优先更新 initial_attraction、comfort、curiosity，也允许轻微更新 trust、anxiety、expectation。
4. major_events 必须能回溯到 transcript 里真实发生过的互动。
5. next_tension 必须连接到下一场自由交流，而不是最终关系判断。
""".strip()

DEFAULT_EVALUATION_FOCUS = ["initial_attraction", "comfort", "curiosity"]
DEFAULT_INTENT_TAGS = ["build_comfort"]
DEFAULT_ACTIVE_TENSION = "第一印象已经形成，但真正的来电还要靠下一场自由交流来验证。"
ALLOWED_INTENT_TAGS = {
    "build_comfort",
    "signal_interest",
    "test_chemistry",
    "show_stability",
    "show_humor",
    "gather_signal",
    "protect_self_image",
    "break_ice",
    "observe_reaction",
}


def build_scene_01_context(db: Session, simulation: SimulationRun) -> dict:
    guest_stmt = select(GuestProfile).where(GuestProfile.project_id == simulation.project_id)
    guests = list(db.scalars(guest_stmt).all())
    protagonist = next(guest for guest in guests if guest.role == "protagonist")
    guest_participants = [guest for guest in guests if guest.role == "guest"][:3]

    relationship_stmt = select(RelationshipState).where(
        RelationshipState.simulation_run_id == simulation.id
    )
    relationships = {item.target_guest_id: item for item in db.scalars(relationship_stmt).all()}

    participants = [
        {
            "guest_id": protagonist.id,
            "name": protagonist.name,
            "role": protagonist.role,
        }
    ] + [
        {
            "guest_id": guest.id,
            "name": guest.name,
            "role": guest.role,
        }
        for guest in guest_participants
    ]

    return {
        "scene_id": "scene_01_intro",
        "project_id": simulation.project_id,
        "simulation_id": simulation.id,
        "strategy_cards": simulation.strategy_cards,
        "scene_goal": "建立第一印象和初始吸引力",
        "scene_frame": "阳光房初见，围绕城市通勤和节目第一印象破冰",
        "participants": participants,
        "participant_lookup": {participant["guest_id"]: participant for participant in participants},
        "protagonist": {
            "guest_id": protagonist.id,
            "name": protagonist.name,
            "role": protagonist.role,
            "profile": protagonist.imported_payload,
            "soul_data": protagonist.soul_data,
        },
        "guests": [
            {
                "guest_id": guest.id,
                "name": guest.name,
                "role": guest.role,
                "profile": guest.imported_payload,
                "soul_data": guest.soul_data,
                "relationship_baseline": relationships[guest.id].metrics,
                "relationship_status": relationships[guest.id].status,
                "relationship_notes": relationships[guest.id].notes,
            }
            for guest in guest_participants
        ],
    }


def build_input_summary(context: dict) -> dict:
    return {
        "scene_id": context["scene_id"],
        "simulation_id": context["simulation_id"],
        "project_id": context["project_id"],
        "strategy_cards": context["strategy_cards"],
        "participants": context["participants"],
    }


def plan_scene_01_intro(context: dict) -> tuple[DirectorPlan, dict | str]:
    settings = get_settings()
    if settings.director_provider_mode == "mock" or (
        settings.director_provider_mode == "auto" and not settings.dashscope_api_key
    ):
        plan = build_mock_plan(context)
        return plan, plan.model_dump()

    raw_payload = call_json_llm(
        PLAN_SYSTEM_PROMPT,
        {
            "scene_id": context["scene_id"],
            "scene_goal": context["scene_goal"],
            "scene_frame": context["scene_frame"],
            "strategy_cards": context["strategy_cards"],
            "participants": context["participants"],
            "guest_briefs": [
                {
                    "guest_id": guest["guest_id"],
                    "name": guest["name"],
                    "relationship_baseline": guest["relationship_baseline"],
                    "attachment_style": guest["profile"].get("attachment_style"),
                    "personality_tags": guest["profile"].get("personality_tags", []),
                }
                for guest in context["guests"]
            ],
        },
    )
    normalized = normalize_plan_payload(raw_payload, context)
    return DirectorPlan.model_validate(normalized), raw_payload


def generate_agent_turn(
    context: dict,
    plan: DirectorPlan,
    transcript: list[AgentTurnPayload],
    turn_index: int,
    speaker_guest_id: str,
) -> tuple[AgentTurnPayload, dict | str, dict]:
    speaker = context["participant_lookup"][speaker_guest_id]
    input_payload = build_agent_input(context, plan, transcript, turn_index, speaker_guest_id)
    settings = get_settings()

    if settings.director_provider_mode == "mock" or (
        settings.director_provider_mode == "auto" and not settings.dashscope_api_key
    ):
        turn = build_mock_turn(context, input_payload, turn_index, speaker_guest_id)
        return turn, turn.model_dump(), input_payload

    raw_payload = call_json_llm(AGENT_SYSTEM_PROMPT, input_payload)
    normalized = normalize_turn_payload(raw_payload, context, turn_index, speaker_guest_id)
    return AgentTurnPayload.model_validate(normalized), raw_payload, input_payload


def finalize_scene_01_intro(
    context: dict,
    plan: DirectorPlan,
    transcript: list[AgentTurnPayload],
) -> tuple[SceneRefereeResult, dict | str]:
    settings = get_settings()
    fallback = build_fallback_referee_result(context, plan, transcript)
    if settings.director_provider_mode == "mock" or (
        settings.director_provider_mode == "auto" and not settings.dashscope_api_key
    ):
        return fallback, fallback.model_dump()

    raw_payload = call_json_llm(
        FINALIZE_SYSTEM_PROMPT,
        {
            "scene_id": context["scene_id"],
            "strategy_cards": context["strategy_cards"],
            "scene_goal": context["scene_goal"],
            "active_tension": plan.active_tension,
            "participants": context["participants"],
            "transcript": [message.model_dump() for message in transcript],
        },
    )
    normalized = normalize_referee_payload(raw_payload, context, transcript, fallback)
    return SceneRefereeResult.model_validate(normalized), raw_payload


def build_agent_input(
    context: dict,
    plan: DirectorPlan,
    transcript: list[AgentTurnPayload],
    turn_index: int,
    speaker_guest_id: str,
) -> dict:
    speaker = context["participant_lookup"][speaker_guest_id]
    protagonist_id = context["protagonist"]["guest_id"]
    guest_context = next(
        (guest for guest in context["guests"] if guest["guest_id"] == speaker_guest_id),
        None,
    )
    directive_lookup = {item.guest_id: item.directive for item in plan.agent_directives}
    visible_transcript = [
        {
            "speaker_name": item.speaker_name,
            "utterance": item.utterance,
            "behavior_summary": item.behavior_summary,
            "intent_tags": item.intent_tags,
        }
        for item in transcript[-4:]
    ]
    speaker_visible_relationship = (
        guest_context["relationship_baseline"] if guest_context else None
    )
    public_guest_briefs = [
        {
            "guest_id": guest["guest_id"],
            "name": guest["name"],
            "city": guest["profile"].get("city"),
            "occupation": guest["profile"].get("occupation"),
            "personality_tags": guest["profile"].get("personality_tags", []),
        }
        for guest in context["guests"]
    ]

    return {
        "scene_id": context["scene_id"],
        "scene_goal": context["scene_goal"],
        "scene_frame": context["scene_frame"],
        "turn_index": turn_index,
        "speaker": speaker,
        "directive": directive_lookup.get(
            speaker_guest_id,
            "用自然轻松的一句回应建立第一印象。",
        ),
        "strategy_cards": context["strategy_cards"],
        "visible_context": {
            "active_tension": plan.active_tension,
            "stop_condition": plan.stop_condition,
            "transcript_so_far": visible_transcript,
            "speaker_relationship_to_protagonist": speaker_visible_relationship,
            "public_guest_briefs": public_guest_briefs if speaker["role"] == "protagonist" else None,
            "speaker_private_profile": (
                guest_context["profile"]
                if guest_context
                else context["protagonist"]["profile"]
            ),
            "speaker_role": speaker["role"],
            "protagonist_id": protagonist_id,
        },
    }


def build_mock_plan(context: dict) -> DirectorPlan:
    directives = []
    for guest in context["guests"]:
        style = guest["profile"].get("attachment_style") or "secure"
        if style == "avoidant":
            directive = "用有火花但不过度承诺的回应测试化学反应。"
        elif style == "secure":
            directive = "以稳定接话和轻松观察降低陌生感。"
        else:
            directive = "先给主角安全感，再试着留下可继续聊的钩子。"
        directives.append({"guest_id": guest["guest_id"], "directive": directive})

    turn_order = [context["protagonist"]["guest_id"]] + [guest["guest_id"] for guest in context["guests"]]
    return DirectorPlan(
        scene_id=context["scene_id"],
        scene_goal=context["scene_goal"],
        scene_frame=context["scene_frame"],
        participants=context["participants"],
        turn_order=turn_order,
        agent_directives=directives,
        evaluation_focus=DEFAULT_EVALUATION_FOCUS,
        stop_condition="所有核心参与者完成首次有效互动，初始印象足以进入自由交流。",
        active_tension=DEFAULT_ACTIVE_TENSION,
    )


def build_mock_turn(
    context: dict,
    input_payload: dict,
    turn_index: int,
    speaker_guest_id: str,
) -> AgentTurnPayload:
    speaker = input_payload["speaker"]
    protagonist_name = context["protagonist"]["name"]
    guest_lookup = {guest["guest_id"]: guest for guest in context["guests"]}

    if speaker["role"] == "protagonist":
        utterance = "我在上海做品牌策略，通勤久了就会把早高峰当成性格测试。你们平时谁最能扛早起？"
        return AgentTurnPayload(
            speaker_guest_id=speaker_guest_id,
            speaker_name=speaker["name"],
            turn_index=turn_index,
            utterance=utterance,
            behavior_summary="主动用轻松比喻打开话题，先营造不紧绷的气氛。",
            intent_tags=["break_ice", "build_comfort"],
            target_guest_ids=[guest["guest_id"] for guest in context["guests"][:2]],
            self_observation="先把气氛放松下来，再看谁会自然接住我的梗。",
        )

    guest = guest_lookup[speaker_guest_id]
    style = guest["profile"].get("attachment_style")
    if style == "avoidant":
        utterance = f"我还行，早起像临时接创意提案，先崩两分钟再突然清醒。你这个比喻挺准，{protagonist_name}。"
        behavior = "带一点玩笑感回应，既接住主角话头，也保留自己的轻盈感。"
        intents = ["show_humor", "test_chemistry"]
        observation = "她接梗挺自然，继续聊下去不会无聊。"
    elif style == "secure":
        utterance = "建筑行业要跑现场，早起基本是默认设置了。你把通勤说成性格测试还挺可爱的，至少不会让人太紧张。"
        behavior = "语气稳定克制，先给主角一点被接住的安全感。"
        intents = ["show_stability", "build_comfort"]
        observation = "她愿意先把气氛放轻，这种人通常比较好相处。"
    else:
        utterance = "我一般会先观察大家怎么进入状态，再决定自己要不要多说一点。你今天开场挺聪明，让人比较容易接话。"
        behavior = "保留观察者姿态，但明确给出正向回应。"
        intents = ["observe_reaction", "build_comfort"]
        observation = "她的表达不硬推，会让我更愿意继续看她后面的样子。"

    return AgentTurnPayload(
        speaker_guest_id=speaker_guest_id,
        speaker_name=speaker["name"],
        turn_index=turn_index,
        utterance=utterance,
        behavior_summary=behavior,
        intent_tags=intents,
        target_guest_ids=[context["protagonist"]["guest_id"]],
        self_observation=observation,
    )


def build_fallback_referee_result(
    context: dict,
    plan: DirectorPlan,
    transcript: list[AgentTurnPayload],
) -> SceneRefereeResult:
    major_events = []
    relationship_deltas = []

    protagonist_id = context["protagonist"]["guest_id"]
    for guest in context["guests"]:
        guest_turn = next(
            (item for item in transcript if item.speaker_guest_id == guest["guest_id"]),
            None,
        )
        if guest_turn is None:
            continue

        positive_intents = set(guest_turn.intent_tags)
        attraction_delta = 4
        comfort_delta = 5
        curiosity_delta = 4
        trust_delta = 1
        anxiety_delta = 0
        event_tags = ["value_alignment"]

        if "show_stability" in positive_intents or "build_comfort" in positive_intents:
            comfort_delta += 3
            trust_delta += 2
        if "show_humor" in positive_intents or "test_chemistry" in positive_intents:
            attraction_delta += 3
            curiosity_delta += 3
            event_tags = ["clear_affection"]
        if "observe_reaction" in positive_intents:
            curiosity_delta += 2
        if "protect_self_image" in positive_intents:
            anxiety_delta += 2

        reason = (
            f"{guest['name']}在初见中成功接住了主角的话题，"
            "留下了可继续了解的第一印象。"
        )
        major_events.append(
            SceneEvent(
                title=f"{guest['name']}完成首次有效互动",
                description=guest_turn.behavior_summary,
                event_tags=event_tags,
                target_guest_ids=[protagonist_id, guest["guest_id"]],
            )
        )
        relationship_deltas.append(
            SceneRelationshipDelta(
                guest_id=guest["guest_id"],
                changes={
                    "initial_attraction": clamp_delta(attraction_delta),
                    "comfort": clamp_delta(comfort_delta),
                    "curiosity": clamp_delta(curiosity_delta),
                    "trust": clamp_delta(trust_delta),
                    "anxiety": clamp_delta(anxiety_delta),
                },
                reason=reason,
            )
        )

    return SceneRefereeResult(
        scene_id=context["scene_id"],
        scene_summary="初见回合完成，主角和几位嘉宾都形成了不同风格的第一印象，关系仍处于可逆的早期偏置阶段。",
        major_events=major_events,
        relationship_deltas=relationship_deltas,
        next_tension="下一场自由交流会检验谁的好感只是礼貌，谁真的愿意继续靠近。",
    )


def normalize_plan_payload(raw_payload: dict | str, context: dict) -> dict:
    payload = ensure_dict(raw_payload)
    participant_lookup = {
        participant["guest_id"]: participant
        for participant in context["participants"]
    }
    name_lookup = {
        participant["name"]: participant["guest_id"]
        for participant in context["participants"]
    }
    protagonist_id = context["protagonist"]["guest_id"]
    guest_ids = [guest["guest_id"] for guest in context["guests"]]

    raw_turn_order = payload.get("turn_order")
    turn_order: list[str] = []
    if isinstance(raw_turn_order, Iterable) and not isinstance(raw_turn_order, (str, bytes)):
        for item in raw_turn_order:
            normalized = normalize_participant_token(item, participant_lookup, name_lookup)
            if normalized and normalized not in turn_order:
                turn_order.append(normalized)

    if protagonist_id not in turn_order:
        turn_order.insert(0, protagonist_id)
    for guest_id in guest_ids:
        if guest_id not in turn_order:
            turn_order.append(guest_id)
    turn_order = [protagonist_id] + [guest_id for guest_id in turn_order if guest_id != protagonist_id]
    turn_order = turn_order[: 1 + len(guest_ids)]

    raw_directives = payload.get("agent_directives", [])
    directives = []
    if isinstance(raw_directives, dict):
        raw_directives = [
            {"guest_id": guest_id, "directive": directive}
            for guest_id, directive in raw_directives.items()
        ]
    if isinstance(raw_directives, list):
        for item in raw_directives:
            if not isinstance(item, dict):
                continue
            guest_id = normalize_participant_token(
                item.get("guest_id") or item.get("name"),
                participant_lookup,
                name_lookup,
            )
            if guest_id and guest_id != protagonist_id:
                directives.append(
                    {
                        "guest_id": guest_id,
                        "directive": clean_text(item.get("directive")) or "以自然回应降低陌生感。",
                    }
                )
    existing_directives = {item["guest_id"] for item in directives}
    for guest in context["guests"]:
        if guest["guest_id"] not in existing_directives:
            directives.append(
                {
                    "guest_id": guest["guest_id"],
                    "directive": "以稳定自然的回应建立第一印象，并为下一场交流留下钩子。",
                }
            )

    participants = [participant_lookup[item["guest_id"]] for item in context["participants"]]
    return {
        "scene_id": context["scene_id"],
        "scene_goal": clean_text(payload.get("scene_goal")) or context["scene_goal"],
        "scene_frame": clean_text(payload.get("scene_frame")) or context["scene_frame"],
        "participants": participants,
        "turn_order": turn_order,
        "agent_directives": directives,
        "evaluation_focus": ensure_string_list(payload.get("evaluation_focus")) or DEFAULT_EVALUATION_FOCUS,
        "stop_condition": clean_text(payload.get("stop_condition"))
        or "所有核心参与者完成首次有效互动，初始印象足以进入自由交流。",
        "active_tension": clean_text(payload.get("active_tension")) or DEFAULT_ACTIVE_TENSION,
    }


def normalize_turn_payload(
    raw_payload: dict | str,
    context: dict,
    turn_index: int,
    speaker_guest_id: str,
) -> dict:
    payload = ensure_dict(raw_payload)
    speaker = context["participant_lookup"][speaker_guest_id]
    utterance = clean_text(payload.get("utterance"))
    if not utterance:
        utterance = clean_text(payload.get("dialogue")) or clean_text(payload.get("message"))
    if not utterance:
        utterance = "先用轻松的一句话回应对方，再观察现场的反馈。"

    behavior_summary = clean_text(payload.get("behavior_summary"))
    if not behavior_summary:
        behavior_summary = "保持自然交流，不抢戏，但明确表达自己的在场感。"

    target_guest_ids = ensure_string_list(payload.get("target_guest_ids"))
    normalized_targets = []
    for item in target_guest_ids:
        guest_id = normalize_participant_token(
            item,
            context["participant_lookup"],
            {participant["name"]: participant["guest_id"] for participant in context["participants"]},
        )
        if guest_id and guest_id != speaker_guest_id and guest_id not in normalized_targets:
            normalized_targets.append(guest_id)
    if not normalized_targets:
        default_target = (
            [context["protagonist"]["guest_id"]]
            if speaker["role"] == "guest"
            else [guest["guest_id"] for guest in context["guests"][:2]]
        )
        normalized_targets = default_target

    intent_tags = [
        tag
        for tag in ensure_string_list(payload.get("intent_tags"))
        if tag in ALLOWED_INTENT_TAGS
    ]
    if not intent_tags:
        intent_tags = DEFAULT_INTENT_TAGS

    return {
        "speaker_guest_id": speaker_guest_id,
        "speaker_name": speaker["name"],
        "turn_index": turn_index,
        "utterance": utterance,
        "behavior_summary": behavior_summary,
        "intent_tags": intent_tags[:3],
        "target_guest_ids": normalized_targets,
        "self_observation": clean_text(payload.get("self_observation")),
    }


def normalize_referee_payload(
    raw_payload: dict | str,
    context: dict,
    transcript: list[AgentTurnPayload],
    fallback: SceneRefereeResult,
) -> dict:
    payload = ensure_dict(raw_payload)
    participant_lookup = context["participant_lookup"]
    name_lookup = {participant["name"]: participant["guest_id"] for participant in context["participants"]}

    major_events = []
    raw_events = payload.get("major_events", [])
    if isinstance(raw_events, list):
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            target_ids = []
            for target in ensure_string_list(item.get("target_guest_ids")):
                guest_id = normalize_participant_token(target, participant_lookup, name_lookup)
                if guest_id and guest_id not in target_ids:
                    target_ids.append(guest_id)
            major_events.append(
                {
                    "title": clean_text(item.get("title")) or "初见互动完成",
                    "description": clean_text(item.get("description")),
                    "event_tags": ensure_string_list(item.get("event_tags")),
                    "target_guest_ids": target_ids,
                }
            )

    raw_deltas = payload.get("relationship_deltas", [])
    normalized_deltas = []
    if isinstance(raw_deltas, dict):
        raw_deltas = [
            {"guest_id": guest_id, **value}
            for guest_id, value in raw_deltas.items()
            if isinstance(value, dict)
        ]
    if isinstance(raw_deltas, list):
        for item in raw_deltas:
            if not isinstance(item, dict):
                continue
            guest_id = normalize_participant_token(
                item.get("guest_id") or item.get("guest_name"),
                participant_lookup,
                name_lookup,
            )
            if not guest_id or guest_id == context["protagonist"]["guest_id"]:
                continue
            raw_changes = item.get("changes", item)
            if not isinstance(raw_changes, dict):
                continue
            changes = {}
            for key, value in raw_changes.items():
                if key in {"guest_id", "guest_name", "reason"}:
                    continue
                if isinstance(value, (int, float)):
                    changes[key] = clamp_delta(int(value))
            if not changes:
                continue
            normalized_deltas.append(
                {
                    "guest_id": guest_id,
                    "changes": changes,
                    "reason": clean_text(item.get("reason")) or "本轮互动形成了稳定的第一印象变化。",
                }
            )

    fallback_payload = fallback.model_dump()
    fallback_delta_lookup = {
        item["guest_id"]: item for item in fallback_payload["relationship_deltas"]
    }
    for guest in context["guests"]:
        if guest["guest_id"] not in {item["guest_id"] for item in normalized_deltas}:
            normalized_deltas.append(fallback_delta_lookup[guest["guest_id"]])

    if not major_events:
        major_events = fallback_payload["major_events"]

    return {
        "scene_id": context["scene_id"],
        "scene_summary": clean_text(payload.get("scene_summary")) or fallback.scene_summary,
        "major_events": major_events,
        "relationship_deltas": normalized_deltas,
        "next_tension": clean_text(payload.get("next_tension")) or fallback.next_tension,
    }


def call_json_llm(system_prompt: str, payload: dict) -> dict | str:
    settings = get_settings()
    client = OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
    )
    completion = client.chat.completions.create(
        model=settings.director_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty content.")
    return parse_json_content(content)


def parse_json_content(content: str) -> dict | str:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.S)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(content[start : end + 1])

    return content


def ensure_dict(raw_payload: dict | str) -> dict:
    if isinstance(raw_payload, dict):
        return raw_payload
    parsed = parse_json_content(raw_payload)
    if isinstance(parsed, dict):
        return parsed
    return {}


def ensure_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [clean_text(item) for item in value.split(",") if clean_text(item)]
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    return []


def clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def normalize_participant_token(
    value: object,
    participant_lookup: dict[str, dict],
    name_lookup: dict[str, str],
) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if text in participant_lookup:
        return text
    if text in name_lookup:
        return name_lookup[text]
    lowered = text.lower()
    if lowered == "protagonist":
        for guest_id, participant in participant_lookup.items():
            if participant["role"] == "protagonist":
                return guest_id
    for guest_id, participant in participant_lookup.items():
        if participant["name"].lower() == lowered:
            return guest_id
    return None


def clamp_delta(value: int) -> int:
    return max(-18, min(18, value))
