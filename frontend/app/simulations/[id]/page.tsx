"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getSimulationOverview, SimulationOverview } from "../../../lib/api";
import { formatMetricLabel, formatStatusLabel } from "../../../lib/presentation";

function formatTime(value?: string) {
  if (!value) {
    return "尚未完成";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function summarizeAuditPayload(logType: string, payload: unknown) {
  if (payload == null || typeof payload !== "object") {
    return "本阶段已记录结构化结果。";
  }

  const record = payload as Record<string, unknown>;
  if (logType === "director_input_summary") {
    const participants = Array.isArray(record.participants)
      ? record.participants
          .map((item) => (typeof item === "object" && item ? String((item as { name?: string }).name ?? "") : ""))
          .filter(Boolean)
      : [];
    return `Director 读取了 ${participants.join("、")} 的场景上下文，并锁定策略卡输入。`;
  }

  if (logType === "director_plan_validated") {
    const directives = Array.isArray(record.agent_directives)
      ? record.agent_directives.length
      : 0;
    return `Director plan 已完成规范化，当前场景共下发 ${directives} 条 guest directive。`;
  }

  if (logType === "guest_agent_outputs") {
    const messages = Array.isArray(record.messages) ? record.messages.length : 0;
    return `多 Agent turn loop 已完成，共生成 ${messages} 轮可回放发言。`;
  }

  if (logType === "scene_referee_result") {
    return typeof record.scene_summary === "string"
      ? record.scene_summary
      : "Referee 已完成本场的结构化收束。";
  }

  if (logType === "applied_state_changes") {
    const deltas = Array.isArray(record.relationship_deltas) ? record.relationship_deltas.length : 0;
    return `状态引擎已应用 ${deltas} 组关系变化，并生成新的 snapshot。`;
  }

  return "该阶段已写入审计日志。";
}

export default function SimulationOverviewPage() {
  const params = useParams<{ id: string }>();
  const simulationId = params.id;
  const [data, setData] = useState<SimulationOverview | null>(null);
  const [error, setError] = useState("");
  const latestScene = data
    ? data.scene_timeline_preview[data.scene_timeline_preview.length - 1]
    : null;

  useEffect(() => {
    let stopped = false;

    async function load() {
      try {
        const nextData = await getSimulationOverview(simulationId);
        if (!stopped) {
          setData(nextData);
          setError("");
        }
      } catch (loadError) {
        if (!stopped) {
          setError(loadError instanceof Error ? loadError.message : "加载模拟失败");
        }
      }
    }

    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [simulationId]);

  return (
    <main className="app-shell">
      <section className="app-header">
        <div>
          <span className="eyebrow">Simulation Overview</span>
          <h1>多 Agent 初见总览</h1>
          <p>
            看当前 scene runtime 处于哪一步、谁在升温、谁只是礼貌回应，再决定深入看 scene
            回放还是 relationship 面板。
          </p>
        </div>
        <div className="header-actions">
          <Link className="ghost-link" href="/">
            创建新实验
          </Link>
          <Link className="ghost-link" href={`/simulations/${simulationId}/relationships`}>
            查看 Relationships
          </Link>
        </div>
      </section>

      {error ? <p className="inline-error">{error}</p> : null}

      {!data ? (
        <section className="content-card">
          <p>正在加载 simulation overview...</p>
        </section>
      ) : (
        <>
          <section className="overview-grid">
            <article className="content-card overview-hero-card">
              <span className={`status-pill status-${data.status}`}>{formatStatusLabel(data.status)}</span>
              <h2>{data.latest_scene_summary ?? "scene_01_intro 正在准备中"}</h2>
              <p>{data.active_tension ?? "等待 Director 生成场景 tension..."}</p>
              <div className="meta-strip">
                <span>simulation_id: {data.id}</span>
                <span>scene: {data.current_scene_code ?? "pending"}</span>
                <span>started: {formatTime(data.started_at)}</span>
              </div>
              {latestScene ? (
                <Link
                  className="primary-link"
                  href={`/simulations/${simulationId}/scenes/${latestScene.scene_run_id}`}
                >
                  打开 scene 回放
                </Link>
              ) : null}
            </article>

            <article className="content-card compact-stat-card">
              <h3>策略卡</h3>
              <div className="tag-row">
                {data.strategy_cards.map((strategy) => (
                  <span key={strategy} className="soft-tag">
                    {strategy}
                  </span>
                ))}
              </div>
              <p className="card-footnote">{data.latest_audit_snippet ?? "等待下一段 tension。"}</p>
            </article>

            <article className="content-card compact-stat-card">
              <h3>运行状态</h3>
              <ul className="bullet-metrics">
                <li>当前状态：{formatStatusLabel(data.status)}</li>
                <li>当前场景索引：{data.current_scene_index}</li>
                <li>结束时间：{formatTime(data.finished_at)}</li>
              </ul>
            </article>
          </section>

          <section className="two-panel-layout">
            <article className="content-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow subtle">Timeline</span>
                  <h2>Scene 时间线</h2>
                </div>
              </div>
              <div className="timeline-list">
                {data.scene_timeline_preview.map((scene) => (
                  <Link
                    key={scene.scene_run_id}
                    className="timeline-card"
                    href={`/simulations/${simulationId}/scenes/${scene.scene_run_id}`}
                  >
                    <div className="timeline-card-top">
                      <strong>{scene.scene_code}</strong>
                      <span className={`status-pill status-${scene.status}`}>
                        {formatStatusLabel(scene.status)}
                      </span>
                    </div>
                    <p>{scene.summary ?? "场景尚未完成结构化摘要。"}</p>
                    <small>{scene.tension ?? "等待下一段 tension。"}</small>
                  </Link>
                ))}
              </div>
            </article>

            <article className="content-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow subtle">Relationships</span>
                  <h2>当前关系走向</h2>
                </div>
                <Link className="text-link" href={`/simulations/${simulationId}/relationships`}>
                  打开完整关系页
                </Link>
              </div>
              <div className="relationship-stack">
                {data.relationship_cards.map((card) => (
                  <article key={card.guest_id} className="relationship-overview-card">
                    <div className="timeline-card-top">
                      <strong>{card.guest_name}</strong>
                      <span className={`trend-pill trend-${card.trend}`}>
                        {formatStatusLabel(card.trend)}
                      </span>
                    </div>
                    <p>
                      状态：<strong>{formatStatusLabel(card.status)}</strong>
                    </p>
                    <div className="metric-chip-row">
                      {Object.entries(card.surface_metrics).map(([metric, value]) => (
                        <span key={metric} className="metric-chip">
                          {formatMetricLabel(metric)}: {value}
                        </span>
                      ))}
                    </div>
                    <ul className="reason-list">
                      {card.top_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            </article>
          </section>

          <section className="content-card">
            <div className="section-heading">
              <div>
                <span className="eyebrow subtle">Audit</span>
                <h2>最近结构化日志</h2>
              </div>
            </div>
            <div className="audit-grid">
              {data.recent_audit_logs.map((log) => (
                <article key={`${log.log_type}-${log.created_at}`} className="audit-card">
                  <strong>{log.log_type}</strong>
                  <span>{formatTime(log.created_at)}</span>
                  <p>{summarizeAuditPayload(log.log_type, log.payload)}</p>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
