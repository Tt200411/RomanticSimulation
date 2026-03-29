const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type RequestOptions = RequestInit & {
  json?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    body: options.json ? JSON.stringify(options.json) : options.body,
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Request failed");
  }

  return response.json() as Promise<T>;
}

export type ProjectResponse = {
  id: string;
  name: string;
  description?: string;
  guest_count: number;
  created_at: string;
};

export type GuestImportPayload = {
  protagonist: {
    name: string;
    age?: number;
    city?: string;
    occupation?: string;
    background_summary?: string;
    personality_summary?: string;
    attachment_style?: string;
    appearance_tags?: string[];
    personality_tags?: string[];
    preferred_traits?: string[];
    disliked_traits?: string[];
    commitment_goal?: string;
  };
  guests: Array<{
    name: string;
    age?: number;
    city?: string;
    occupation?: string;
    background_summary?: string;
    personality_summary?: string;
    attachment_style?: string;
    appearance_tags?: string[];
    personality_tags?: string[];
    preferred_traits?: string[];
    disliked_traits?: string[];
    commitment_goal?: string;
  }>;
};

export type SceneTimelinePreview = {
  scene_run_id: string;
  scene_code: string;
  scene_index: number;
  status: string;
  summary?: string;
  tension?: string;
  replay_url?: string;
};

export type RelationshipCard = {
  guest_id: string;
  guest_name: string;
  status: string;
  trend: string;
  top_reasons: string[];
  surface_metrics: Record<string, number>;
};

export type SimulationOverview = {
  id: string;
  project_id: string;
  status: string;
  current_scene_index: number;
  current_scene_code?: string;
  latest_scene_summary?: string;
  latest_audit_snippet?: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  strategy_cards: string[];
  active_tension?: string;
  latest_scene_replay_url?: string;
  scene_timeline_preview: SceneTimelinePreview[];
  relationship_cards: RelationshipCard[];
  recent_audit_logs: Array<{ log_type: string; payload: unknown; created_at: string }>;
};

export type SceneReplay = {
  simulation_id: string;
  scene_run_id: string;
  scene_code: string;
  scene_index: number;
  status: string;
  summary?: string;
  scene_plan?: {
    scene_id: string;
    scene_goal: string;
    scene_frame: string;
    participants: Array<{ guest_id: string; name: string; role: string }>;
    turn_order: string[];
    agent_directives: Array<{ guest_id: string; directive: string }>;
    evaluation_focus: string[];
    stop_condition: string;
    active_tension: string;
  };
  messages: Array<{
    speaker_guest_id: string;
    speaker_name: string;
    turn_index: number;
    utterance: string;
    behavior_summary: string;
    intent_tags: string[];
    target_guest_ids: string[];
    self_observation?: string | null;
  }>;
  major_events: Array<{
    title: string;
    description?: string | null;
    event_tags: string[];
    target_guest_ids: string[];
  }>;
  relationship_deltas: Array<{
    guest_id: string;
    changes: Record<string, number>;
    reason: string;
  }>;
  next_tension?: string;
  replay_url?: string;
};

export type SimulationTimeline = {
  simulation_id: string;
  scenes: SceneTimelinePreview[];
};

export type SimulationRelationships = {
  simulation_id: string;
  relationships: RelationshipCard[];
};

export async function createProject(payload: {
  name: string;
  description?: string;
}) {
  return request<ProjectResponse>("/projects", {
    method: "POST",
    json: payload,
  });
}

export async function importGuests(projectId: string, payload: GuestImportPayload) {
  return request(`/projects/${projectId}/guests/import`, {
    method: "POST",
    json: payload,
  });
}

export async function createSimulation(projectId: string, strategyCards: string[]) {
  return request<{
    id: string;
  }>(`/projects/${projectId}/simulations`, {
    method: "POST",
    json: { strategy_cards: strategyCards },
  });
}

export async function getSimulationOverview(simulationId: string) {
  return request<SimulationOverview>(`/simulations/${simulationId}`);
}

export async function getSimulationTimeline(simulationId: string) {
  return request<SimulationTimeline>(`/simulations/${simulationId}/timeline`);
}

export async function getSimulationRelationships(simulationId: string) {
  return request<SimulationRelationships>(`/simulations/${simulationId}/relationships`);
}

export async function getSceneReplay(simulationId: string, sceneRunId: string) {
  return request<SceneReplay>(`/simulations/${simulationId}/scenes/${sceneRunId}`);
}
