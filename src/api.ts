import type {
  AssistantConfig,
  GeneratePayload,
  Insights,
  Job,
  Page,
  Presets,
  Provider,
  ProviderDraft,
  RuntimeConfig,
  RuntimeInfo,
  Settings,
  Stats,
  StudioImage,
  SubmitResponse,
} from "./types";

interface FeedbackRequest {
  rating?: number;
  favorite?: boolean;
  notes?: string;
  tags?: string[];
}

export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;

  constructor(message: string, status = 0, code = "network_error", hint = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.hint = hint;
  }
}

class StudioApi {
  base = "http://127.0.0.1:8765";
  token = "";

  configure(config: RuntimeConfig) {
    this.base = config.api.replace(/\/$/, "");
    this.token = config.token;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.token) headers.set("X-Lumen-Token", this.token);
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    let response: Response;
    try {
      response = await fetch(`${this.base}${path}`, { ...init, headers });
    } catch (error) {
      throw new ApiError("无法连接本地服务", 0, "backend_unreachable", String(error));
    }
    if (!response.ok) {
      let body: { detail?: string; code?: string; hint?: string } = {};
      try {
        body = await response.json();
      } catch {
        body = { detail: response.statusText };
      }
      throw new ApiError(body.detail || `请求失败（${response.status}）`, response.status, body.code || "http_error", body.hint || "");
    }
    if (response.status === 204) return {} as T;
    return (await response.json()) as T;
  }

  mediaUrl(path: string | undefined, options: { thumb?: boolean; download?: boolean } = {}): string {
    if (!path) return "";
    let url = path.startsWith("http") ? path : `${this.base}${path}`;
    const parsed = new URL(url);
    if (this.token) parsed.searchParams.set("token", this.token);
    if (options.thumb) parsed.searchParams.set("thumb", "1");
    if (options.download) parsed.searchParams.set("download", "1");
    return parsed.toString();
  }

  imageUrl(image: Pick<StudioImage, "id">, thumb = false): string {
    return this.mediaUrl(`/api/images/${image.id}/file`, { thumb });
  }

  health() {
    return this.request<{ status: string; version: string }>("/api/health");
  }

  runtime() {
    return this.request<RuntimeInfo>("/api/runtime");
  }

  presets() {
    return this.request<Presets>("/api/meta/presets");
  }

  settings() {
    return this.request<Settings>("/api/settings");
  }

  updateSettings(patch: Partial<Settings> | Record<string, unknown>) {
    return this.request<Settings>("/api/settings", { method: "PATCH", body: JSON.stringify(patch) });
  }

  providers() {
    return this.request<Provider[]>("/api/providers");
  }

  saveProvider(draft: ProviderDraft) {
    const path = draft.id ? `/api/providers/${draft.id}` : "/api/providers";
    return this.request<Provider>(path, {
      method: draft.id ? "PUT" : "POST",
      body: JSON.stringify(draft),
    });
  }

  deleteProvider(id: string) {
    return this.request<{ ok: boolean }>(`/api/providers/${id}`, { method: "DELETE" });
  }

  testProvider(id: string) {
    return this.request<{ ok: boolean; message: string; detail?: string; models?: string[]; free_vram_mb?: number }>(
      `/api/providers/${id}/test`,
      { method: "POST" },
    );
  }

  providerModels(id: string) {
    return this.request<{ models: string[] }>(`/api/providers/${id}/models`);
  }

  setDefaultProvider(id: string) {
    return this.request<{ ok: boolean }>(`/api/providers/${id}/default`, { method: "POST" });
  }

  generate(payload: GeneratePayload) {
    return this.request<SubmitResponse>("/api/generate", { method: "POST", body: JSON.stringify(payload) });
  }

  job(id: string) {
    return this.request<Job>(`/api/jobs/${id}`);
  }

  cancelJob(id: string) {
    return this.request<{ ok: boolean; message: string }>(`/api/jobs/${id}/cancel`, { method: "POST" });
  }

  images(params: Record<string, string | number | boolean | undefined>) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return this.request<Page<StudioImage>>(`/api/images?${query.toString()}`);
  }

  image(id: string) {
    return this.request<StudioImage>(`/api/images/${id}`);
  }

  feedback(id: string, payload: FeedbackRequest) {
    return this.request<{ image: StudioImage; feedback_count: number }>(`/api/images/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  patchImage(id: string, payload: { favorite?: boolean; notes?: string; tags?: string[] }) {
    return this.request<StudioImage>(`/api/images/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
  }

  cropImage(id: string, box: { x: number; y: number; width: number; height: number }) {
    return this.request<StudioImage>(`/api/images/${id}/crop`, { method: "POST", body: JSON.stringify(box) });
  }

  revealImage(id: string) {
    return this.request<{ path: string }>(`/api/images/${id}/reveal`);
  }

  deleteImage(id: string) {
    return this.request<{ ok: boolean }>(`/api/images/${id}`, { method: "DELETE" });
  }

  insights() {
    return this.request<Insights>("/api/learning/insights");
  }

  trainLearning() {
    return this.request<{ ok: boolean; insights: Insights }>("/api/learning/train", { method: "POST" });
  }

  resetLearning() {
    return this.request<{ ok: boolean }>("/api/learning/reset", { method: "POST" });
  }

  enhancePrompt(prompt: string, style: string) {
    return this.request<{ prompt: string; added_style: boolean; learned_tokens: string[]; learned_negative: string[] }>(
      "/api/prompt/enhance",
      { method: "POST", body: JSON.stringify({ prompt, style, enhance: true }) },
    );
  }

  assistant() {
    return this.request<AssistantConfig>("/api/assistant");
  }

  updateAssistant(payload: Partial<AssistantConfig> & { api_key?: string; clear_key?: boolean }) {
    return this.request<AssistantConfig>("/api/assistant", { method: "PUT", body: JSON.stringify(payload) });
  }

  testAssistant() {
    return this.request<{ ok: boolean; message: string; detail?: string; models: string[] }>("/api/assistant/test", {
      method: "POST",
    });
  }

  assistantEnhance(prompt: string, style: string, mode = "txt2img") {
    return this.request<{ prompt: string; negative_prompt: string; raw: string; model: string; style: string }>(
      "/api/assistant/enhance",
      { method: "POST", body: JSON.stringify({ prompt, style, mode }) },
    );
  }

  installRuntime(variant: "auto" | "cuda" | "cpu") {
    return this.request<{ ok: boolean; message: string; status: RuntimeInfo["install"] }>("/api/runtime/install", {
      method: "POST",
      body: JSON.stringify({ variant }),
    });
  }

  cancelRuntimeInstall() {
    return this.request<{ ok: boolean; message: string }>("/api/runtime/cancel-install", { method: "POST" });
  }

  localModels() {
    return this.request<{ models: { id: string; path: string; size_gb: number }[] }>("/api/runtime/models");
  }

  stats() {
    return this.request<Stats>("/api/stats");
  }
}

export const api = new StudioApi();
