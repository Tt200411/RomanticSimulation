"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  getSimulationRelationships,
  SimulationRelationships,
} from "../../../../lib/api";
import { formatMetricLabel, formatStatusLabel } from "../../../../lib/presentation";

export default function RelationshipsPage() {
  const params = useParams<{ id: string }>();
  const simulationId = params.id;
  const [data, setData] = useState<SimulationRelationships | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;

    async function load() {
      try {
        const nextData = await getSimulationRelationships(simulationId);
        if (!stopped) {
          setData(nextData);
          setError("");
        }
      } catch (loadError) {
        if (!stopped) {
          setError(loadError instanceof Error ? loadError.message : "加载关系面板失败");
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
          <span className="eyebrow">Relationships</span>
          <h1>关系温度与理由面板</h1>
          <p>把 attraction、comfort、trust、curiosity、anxiety 收敛成可读的关系卡，而不是裸 JSON。</p>
        </div>
        <div className="header-actions">
          <Link className="ghost-link" href={`/simulations/${simulationId}`}>
            返回总览
          </Link>
        </div>
      </section>

      {error ? <p className="inline-error">{error}</p> : null}
      {!data ? (
        <section className="content-card">
          <p>正在加载 relationships...</p>
        </section>
      ) : (
        <section className="relationship-page-grid">
          {data.relationships.map((relationship) => (
            <article key={relationship.guest_id} className="relationship-detail-card">
              <div className="timeline-card-top">
                <div>
                  <span className="eyebrow subtle">Guest</span>
                  <h2>{relationship.guest_name}</h2>
                </div>
                <span className={`trend-pill trend-${relationship.trend}`}>
                  {formatStatusLabel(relationship.trend)}
                </span>
              </div>

              <p className="relationship-status-line">
                当前状态：<strong>{formatStatusLabel(relationship.status)}</strong>
              </p>

              <div className="metric-bar-list">
                {Object.entries(relationship.surface_metrics).map(([metric, value]) => (
                  <div key={metric} className="metric-bar-row">
                    <div className="metric-bar-header">
                      <span>{formatMetricLabel(metric)}</span>
                      <strong>{value}</strong>
                    </div>
                    <div className="metric-bar-track">
                      <div className="metric-bar-fill" style={{ width: `${Math.min(value, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="reason-block">
                <h3>Top Reasons</h3>
                <ul className="reason-list">
                  {relationship.top_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
