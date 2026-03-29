const statusLabels: Record<string, string> = {
  queued: "排队中",
  claimed: "已领取",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  observing: "观察中",
  warming: "轻微升温",
  heating_up: "明显升温",
  unstable: "有火花但不稳",
  cooling: "正在降温",
  blocked: "被卡住",
  out: "基本出局",
  paired: "形成互选",
};

const metricLabels: Record<string, string> = {
  initial_attraction: "初始吸引",
  comfort: "舒适度",
  trust: "信任",
  curiosity: "探索意愿",
  anxiety: "焦虑",
};

export function formatStatusLabel(value: string) {
  return statusLabels[value] ?? value;
}

export function formatMetricLabel(value: string) {
  return metricLabels[value] ?? value;
}
