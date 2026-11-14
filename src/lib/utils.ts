export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

export function formatDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function relativeTime(value: string): string {
  if (!value) return "";
  const date = new Date(value).getTime();
  if (Number.isNaN(date)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - date) / 1000));
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

export function formatMs(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} 秒`;
  return `${Math.floor(ms / 60_000)} 分 ${Math.round((ms % 60_000) / 1000)} 秒`;
}

export function formatBytes(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return "—";
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function formatVram(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return "—";
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function ratioLabel(width: number, height: number): string {
  const ratio = width / height;
  const presets: Array<[number, string]> = [
    [1, "1:1"],
    [4 / 3, "4:3"],
    [3 / 4, "3:4"],
    [3 / 2, "3:2"],
    [2 / 3, "2:3"],
    [16 / 9, "16:9"],
    [9 / 16, "9:16"],
    [21 / 9, "21:9"],
  ];
  return presets.find(([value]) => Math.abs(value - ratio) < 0.02)?.[1] ?? `${ratio.toFixed(2)}:1`;
}

export function aspectBoxStyle(ratio: number): { width: string; height: string } {
  if (ratio >= 1) return { width: "26px", height: `${Math.max(9, Math.round(26 / ratio))}px` };
  return { width: `${Math.max(9, Math.round(26 * ratio))}px`, height: "26px" };
}

export function ratingLabel(rating: number | null): string {
  if (!rating) return "未评分";
  return ["", "较差", "一般", "还行", "喜欢", "很喜欢"][rating] ?? "未评分";
}

export function truncate(value: string, length: number): string {
  if (value.length <= length) return value;
  return `${value.slice(0, length - 1)}…`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
