"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  createProject,
  createSimulation,
  GuestImportPayload,
  importGuests,
} from "../lib/api";

const sampleGuestPayload: GuestImportPayload = {
  protagonist: {
    name: "林夏",
    age: 27,
    city: "Shanghai",
    occupation: "Brand Strategist",
    background_summary: "第一次参加恋综，希望找到稳定又能真实表达情绪的关系。",
    personality_summary: "外冷内热，慢热但对有趣的人会主动靠近。",
    attachment_style: "anxious",
    appearance_tags: ["clean", "stylish", "athletic"],
    personality_tags: ["observant", "humorous", "sincere"],
    preferred_traits: ["emotionally_stable", "humorous", "proactive", "sincere"],
    disliked_traits: ["cold", "ambiguous"],
    commitment_goal: "serious_relationship",
  },
  guests: [
    {
      name: "周予安",
      age: 29,
      city: "Shanghai",
      occupation: "Architect",
      background_summary: "节奏稳，安全感强，讨厌没有边界感的暧昧。",
      personality_summary: "克制温和，表达不快但观察力强。",
      attachment_style: "secure",
      appearance_tags: ["clean", "gentle", "minimal"],
      personality_tags: ["emotionally_stable", "humorous", "patient"],
      preferred_traits: ["warm", "clear", "kind"],
      disliked_traits: ["dramatic"],
      commitment_goal: "serious_relationship",
    },
    {
      name: "陈屿",
      age: 26,
      city: "Hangzhou",
      occupation: "Content Director",
      background_summary: "强表达欲，喜欢有火花的互动。",
      personality_summary: "会主动调动气氛，但在认真关系里怕被束缚。",
      attachment_style: "avoidant",
      appearance_tags: ["fashionable", "playful", "sharp"],
      personality_tags: ["creative", "direct", "playful"],
      preferred_traits: ["confident", "interesting"],
      disliked_traits: ["clingy"],
      commitment_goal: "observe_first",
    },
    {
      name: "沈知意",
      age: 28,
      city: "Beijing",
      occupation: "Product Manager",
      background_summary: "理性克制，重视长期价值观一致。",
      personality_summary: "沟通清晰，喜欢把复杂关系说透。",
      attachment_style: "secure",
      appearance_tags: ["sharp", "elegant"],
      personality_tags: ["proactive", "clear", "emotionally_stable"],
      preferred_traits: ["clear", "stable", "growth_oriented"],
      disliked_traits: ["avoidant"],
      commitment_goal: "serious_relationship",
    },
  ],
};

const strategyOptions = [
  {
    id: "warm_presence",
    title: "暖场在场感",
    description: "降低陌生感，优先做出让人愿意接近的第一印象。",
  },
  {
    id: "playful_opening",
    title: "俏皮开场",
    description: "提高好奇心和火花感，但更依赖临场接梗能力。",
  },
  {
    id: "quiet_observation",
    title: "安静观察",
    description: "控制失误，先看场上反馈，但也可能错过存在感。",
  },
];

export default function HomePage() {
  const router = useRouter();
  const [projectName, setProjectName] = useState("恋爱模拟器 Phase 2 实验");
  const [description, setDescription] = useState("scene_01_intro 多 Agent runtime");
  const [guestJson, setGuestJson] = useState(JSON.stringify(sampleGuestPayload, null, 2));
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([
    "warm_presence",
    "playful_opening",
  ]);
  const [status, setStatus] = useState("准备启动第一轮多 Agent 初见。");
  const [error, setError] = useState("");
  const [isLaunching, setIsLaunching] = useState(false);

  const parsedPayload = useMemo(() => {
    try {
      return JSON.parse(guestJson) as GuestImportPayload;
    } catch {
      return null;
    }
  }, [guestJson]);

  function toggleStrategy(strategyId: string) {
    setSelectedStrategies((current) => {
      if (current.includes(strategyId)) {
        return current.filter((item) => item !== strategyId);
      }
      if (current.length >= 2) {
        return [current[1], strategyId];
      }
      return [...current, strategyId];
    });
  }

  async function handleLaunchSimulation() {
    if (!parsedPayload) {
      setError("高级 JSON 不是合法格式，无法创建实验。");
      return;
    }

    try {
      setIsLaunching(true);
      setError("");
      setStatus("正在创建实验项目...");
      const project = await createProject({
        name: projectName,
        description,
      });

      setStatus("正在导入主角与嘉宾档案...");
      await importGuests(project.id, parsedPayload);

      setStatus("正在启动 scene_01_intro 多 Agent 模拟...");
      const simulation = await createSimulation(project.id, selectedStrategies);
      router.push(`/simulations/${simulation.id}`);
    } catch (launchError) {
      setError(launchError instanceof Error ? launchError.message : "启动模拟失败");
      setStatus("实验启动失败，请检查后端日志后重试。");
    } finally {
      setIsLaunching(false);
    }
  }

  return (
    <main className="marketing-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">Phase 2 / scene_01_intro</span>
          <h1>把第一印象拆成真正可回放的多 Agent 现场</h1>
          <p className="hero-body">
            这不是再点一次 mock 按钮看 JSON。你会启动一个真实的 scene runtime：
            Director 先做编排，主角和嘉宾逐轮发言，最后由 Referee 收束出关系变化与下一场 tension。
          </p>
          <div className="hero-metrics">
            <article>
              <strong>4 个页面</strong>
              <span>首页、总览、scene 回放、relationships</span>
            </article>
            <article>
              <strong>6 次结构化节点</strong>
              <span>plan、turn loop、finalize、snapshot、timeline、cards</span>
            </article>
            <article>
              <strong>Live 优先</strong>
              <span>默认走 DashScope 兼容接口，而不是只在 mock 自证</span>
            </article>
          </div>
        </div>

        <aside className="launch-panel">
          <div className="panel-header">
            <span className="panel-kicker">New Experiment</span>
            <h2>启动一局 Phase 2 模拟</h2>
          </div>
          <label className="field-label">实验名称</label>
          <input
            className="field-input"
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
          />
          <label className="field-label">实验说明</label>
          <textarea
            className="field-textarea compact"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />

          <div className="status-panel">
            <span className="status-dot" />
            <div>
              <strong>启动状态</strong>
              <p>{status}</p>
            </div>
          </div>

          <button className="primary-button" onClick={handleLaunchSimulation} disabled={isLaunching}>
            {isLaunching ? "正在创建实验..." : "开始第一轮多 Agent 初见"}
          </button>
          {error ? <p className="inline-error">{error}</p> : null}
        </aside>
      </section>

      <section className="home-grid">
        <article className="content-card protagonist-card">
          <div className="card-heading">
            <span className="eyebrow subtle">Protagonist</span>
            <h2>主角设定</h2>
          </div>
          {parsedPayload ? (
            <>
              <div className="identity-line">
                <strong>{parsedPayload.protagonist.name}</strong>
                <span>
                  {parsedPayload.protagonist.age} 岁 · {parsedPayload.protagonist.city} ·{" "}
                  {parsedPayload.protagonist.occupation}
                </span>
              </div>
              <p>{parsedPayload.protagonist.background_summary}</p>
              <div className="tag-row">
                {(parsedPayload.protagonist.personality_tags ?? []).map((tag) => (
                  <span key={tag} className="soft-tag">
                    {tag}
                  </span>
                ))}
              </div>
              <ul className="bullet-metrics">
                <li>依恋风格：{parsedPayload.protagonist.attachment_style}</li>
                <li>关系目标：{parsedPayload.protagonist.commitment_goal}</li>
                <li>偏好特质：{(parsedPayload.protagonist.preferred_traits ?? []).join(" / ")}</li>
              </ul>
            </>
          ) : (
            <p className="inline-error">高级 JSON 解析失败，无法预览主角档案。</p>
          )}
        </article>

        <article className="content-card strategy-card">
          <div className="card-heading">
            <span className="eyebrow subtle">Strategy</span>
            <h2>Scene 01 策略卡</h2>
          </div>
          <p className="card-intro">最多选 2 张策略卡，直接影响 Director 的编排和初见事件倾向。</p>
          <div className="strategy-list">
            {strategyOptions.map((strategy) => {
              const isActive = selectedStrategies.includes(strategy.id);
              return (
                <button
                  key={strategy.id}
                  type="button"
                  className={`strategy-option${isActive ? " active" : ""}`}
                  onClick={() => toggleStrategy(strategy.id)}
                >
                  <span>{strategy.title}</span>
                  <small>{strategy.description}</small>
                </button>
              );
            })}
          </div>
        </article>
      </section>

      <section className="content-card guest-list-card">
        <div className="card-heading">
          <span className="eyebrow subtle">Cast</span>
          <h2>嘉宾阵容预览</h2>
        </div>
        <div className="guest-grid">
          {parsedPayload?.guests.map((guest) => (
            <article key={guest.name} className="guest-preview-card">
              <div className="identity-line stacked">
                <strong>{guest.name}</strong>
                <span>
                  {guest.age} 岁 · {guest.city} · {guest.occupation}
                </span>
              </div>
              <p>{guest.background_summary}</p>
              <div className="tag-row">
                {(guest.personality_tags ?? []).map((tag) => (
                  <span key={tag} className="soft-tag muted">
                    {tag}
                  </span>
                ))}
              </div>
              <div className="mini-meta">
                <span>{guest.attachment_style}</span>
                <span>{guest.commitment_goal}</span>
              </div>
            </article>
          )) ?? <p className="inline-error">高级 JSON 解析失败，无法预览嘉宾。</p>}
        </div>
      </section>

      <section className="content-card">
        <details className="advanced-editor">
          <summary>高级 JSON 编辑器</summary>
          <p className="card-intro">
            默认档案已经可直接运行。只有在你需要替换主角或嘉宾设定时再展开编辑。
          </p>
          <textarea
            className="field-textarea"
            value={guestJson}
            onChange={(event) => setGuestJson(event.target.value)}
          />
        </details>
      </section>
    </main>
  );
}
