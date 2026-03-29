"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getSceneReplay, SceneReplay } from "../../../../../lib/api";
import { formatMetricLabel, formatStatusLabel } from "../../../../../lib/presentation";

export default function SceneReplayPage() {
  const params = useParams<{ id: string; sceneRunId: string }>();
  const simulationId = params.id;
  const sceneRunId = params.sceneRunId;
  const [data, setData] = useState<SceneReplay | null>(null);
  const [error, setError] = useState("");
  const participantNameMap = Object.fromEntries(
    (data?.scene_plan?.participants ?? []).map((participant) => [participant.guest_id, participant.name])
  );

  useEffect(() => {
    let stopped = false;

    async function load() {
      try {
        const nextData = await getSceneReplay(simulationId, sceneRunId);
        if (!stopped) {
          setData(nextData);
          setError("");
        }
      } catch (loadError) {
        if (!stopped) {
          setError(loadError instanceof Error ? loadError.message : "加载 scene 回放失败");
        }
      }
    }

    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [sceneRunId, simulationId]);

  return (
    <main className="app-shell">
      <section className="app-header">
        <div>
          <span className="eyebrow">Scene Replay</span>
          <h1>scene_01_intro 回放页</h1>
          <p>从 Director plan、逐轮对话到 Referee 收束，都在这一页按时序展开。</p>
        </div>
        <div className="header-actions">
          <Link className="ghost-link" href={`/simulations/${simulationId}`}>
            返回总览
          </Link>
          <Link className="ghost-link" href={`/simulations/${simulationId}/relationships`}>
            查看关系卡
          </Link>
        </div>
      </section>

      {error ? <p className="inline-error">{error}</p> : null}
      {!data ? (
        <section className="content-card">
          <p>正在加载 scene replay...</p>
        </section>
      ) : (
        <>
          <section className="overview-grid">
            <article className="content-card overview-hero-card">
              <span className={`status-pill status-${data.status}`}>{formatStatusLabel(data.status)}</span>
              <h2>{data.summary ?? data.scene_code}</h2>
              <p>{data.next_tension ?? "等待下一场 tension。"}</p>
            </article>

            <article className="content-card compact-stat-card">
              <h3>Director Plan</h3>
              <p>{data.scene_plan?.scene_goal ?? "暂无 plan"}</p>
              <p className="card-footnote">{data.scene_plan?.active_tension ?? "等待 active tension。"}</p>
            </article>
          </section>

          {data.scene_plan ? (
            <section className="content-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow subtle">Plan</span>
                  <h2>Director 编排</h2>
                </div>
              </div>
              <div className="plan-grid">
                <article className="plan-block">
                  <strong>Scene Frame</strong>
                  <p>{data.scene_plan.scene_frame}</p>
                </article>
                <article className="plan-block">
                  <strong>Turn Order</strong>
                    <div className="tag-row">
                    {data.scene_plan.turn_order.map((item) => (
                      <span key={item} className="soft-tag">
                        {participantNameMap[item] ?? item}
                      </span>
                    ))}
                  </div>
                </article>
                <article className="plan-block">
                  <strong>Agent Directives</strong>
                  <ul className="reason-list">
                    {data.scene_plan.agent_directives.map((directive) => (
                      <li key={`${directive.guest_id}-${directive.directive}`}>
                        {participantNameMap[directive.guest_id] ?? directive.guest_id}: {directive.directive}
                      </li>
                    ))}
                  </ul>
                </article>
              </div>
            </section>
          ) : null}

          <section className="content-card">
            <div className="section-heading">
              <div>
                <span className="eyebrow subtle">Transcript</span>
                <h2>逐轮回放</h2>
              </div>
            </div>
            <div className="transcript-list">
              {data.messages.map((message) => (
                <article key={`${message.turn_index}-${message.speaker_guest_id}`} className="message-card">
                  <div className="timeline-card-top">
                    <strong>
                      Turn {message.turn_index} · {message.speaker_name}
                    </strong>
                    <div className="tag-row">
                      {message.intent_tags.map((tag) => (
                        <span key={tag} className="soft-tag muted">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <p className="utterance-block">“{message.utterance}”</p>
                  <p>{message.behavior_summary}</p>
                  {message.self_observation ? (
                    <p className="card-footnote">Self observation: {message.self_observation}</p>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          <section className="two-panel-layout">
            <article className="content-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow subtle">Events</span>
                  <h2>关键事件</h2>
                </div>
              </div>
              <div className="timeline-list">
                {data.major_events.map((event) => (
                  <article key={event.title} className="timeline-card static">
                    <strong>{event.title}</strong>
                    <p>{event.description ?? "本轮互动已被裁决为关键事件。"}</p>
                    <div className="tag-row">
                      {event.event_tags.map((tag) => (
                        <span key={tag} className="soft-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </article>

            <article className="content-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow subtle">Deltas</span>
                  <h2>关系变化</h2>
                </div>
              </div>
              <div className="timeline-list">
                {data.relationship_deltas.map((delta) => (
                  <article key={delta.guest_id} className="timeline-card static">
                    <strong>{participantNameMap[delta.guest_id] ?? delta.guest_id}</strong>
                    <div className="metric-chip-row">
                      {Object.entries(delta.changes).map(([key, value]) => (
                        <span key={key} className="metric-chip">
                          {formatMetricLabel(key)}: {value > 0 ? "+" : ""}
                          {value}
                        </span>
                      ))}
                    </div>
                    <p>{delta.reason}</p>
                  </article>
                ))}
              </div>
            </article>
          </section>
        </>
      )}
    </main>
  );
}
