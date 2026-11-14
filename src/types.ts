export type PageId = "create" | "gallery" | "models" | "learning" | "settings";

export interface Availability {
  available: boolean;
  reason: string;
  detail: string;
  version?: string;
  installable?: boolean;
}

export interface LocalModel {
  id: string;
  label: string;
  family: string;
  download_gb: number;
  min_vram_mb: number;
  comfort_vram_mb: number;
  default_edge: number;
  license: string;
  note: string;
}

export interface Provider {
  id: string;
  name: string;
  kind: "diffusers" | "comfyui" | "openai" | "stability" | "demo";
  kind_label: string;
  base_url: string;
  model: string;
  enabled: boolean;
  is_default: boolean;
  options: Record<string, unknown>;
  secret_set: boolean;
  secret_masked: string;
  availability: Availability;
  model_catalog?: LocalModel[];
  created_at: string;
  updated_at: string;
}

export interface ProviderDraft {
  id?: string;
  name: string;
  kind: Provider["kind"];
  base_url: string;
  model: string;
  enabled: boolean;
  is_default?: boolean;
  options: Record<string, unknown>;
  api_key?: string;
  clear_secret?: boolean;
}

export interface AspectPreset {
  id: string;
  label: string;
  ratio: number;
  hint: string;
}

export interface StylePreset {
  id: string;
  label: string;
  accent: string;
}

export interface SchedulerPreset {
  id: string;
  label: string;
}

export interface HardwareTier {
  id: string;
  label: string;
  cpu: string;
  ram: string;
  gpu: string;
  vram: string;
  experience: string;
}

export interface Presets {
  app: { name: string; version: string };
  styles: StylePreset[];
  aspects: AspectPreset[];
  schedulers: SchedulerPreset[];
  provider_kinds: { id: Provider["kind"]; label: string }[];
  local_models: LocalModel[];
  hardware: {
    detected: {
      vendor: string;
      name: string;
      total_mb: number;
      used_mb: number;
      free_mb: number;
      driver: string;
    }[];
    tiers: HardwareTier[];
  };
}

export interface Analysis {
  version?: number;
  technical_score?: number;
  sharpness?: number;
  exposure?: number;
  contrast?: number;
  saturation?: number;
  colorfulness?: number;
  entropy?: number;
  composition?: number;
  brightness?: number;
  tags?: string[];
  palette?: { hex: string; share: number }[];
  phash?: string;
  duplicate_of?: string;
  duplicate_distance?: number;
}

export interface StudioImage {
  id: string;
  file: string;
  thumb: string;
  mime: string;
  prompt: string;
  negative_prompt: string;
  mode: "txt2img" | "img2img" | "crop";
  provider_id: string;
  provider_name: string;
  model: string;
  width: number;
  height: number;
  steps: number;
  guidance: number;
  seed: number;
  strength: number;
  scheduler: string;
  style: string;
  init_image_id: string | null;
  batch_index: number;
  favorite: boolean;
  rating: number | null;
  notes: string;
  tags: string[];
  analysis: Analysis;
  params: Record<string, unknown>;
  generation_ms: number;
  created_at: string;
  file_url: string;
  thumb_url: string;
}

export interface GenerationTuning {
  steps: number;
  guidance: number;
  scheduler: string;
  style: string;
  confidence: number;
  reason: string;
  explore: boolean;
  samples: number;
  predicted_score: number;
  applied?: { steps: boolean; guidance: boolean; scheduler: boolean };
  source?: string;
}

export interface GenerationResult {
  image_ids: string[];
  images: StudioImage[];
  tuning: GenerationTuning | null;
  warnings: string[];
  resolved_prompt: string;
  resolved_negative: string;
  low_vram: boolean;
  provider_id: string;
  provider_name: string;
  model: string;
  steps: number;
  guidance: number;
  scheduler: string;
  seed: number;
  width: number;
  height: number;
  generation_ms: number;
}

export interface JobError {
  message: string;
  code: string;
  hint: string;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  request: Record<string, unknown>;
  result: (GenerationResult & { images: StudioImage[] }) | null;
  error: JobError | null;
  provider_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  queue_position: number;
}

export interface GeneratePayload {
  prompt: string;
  negative_prompt: string;
  mode: "txt2img" | "img2img";
  provider_id: string;
  model?: string;
  width?: number;
  height?: number;
  aspect_ratio: string;
  long_edge: number;
  steps: number | null;
  guidance: number | null;
  seed: number;
  strength: number;
  batch_size: number;
  scheduler: string;
  style: string;
  init_image?: string;
  init_image_id?: string;
  auto_tune: boolean;
  enhance_prompt: boolean;
  cel_shading?: boolean;
}

export interface SubmitResponse {
  job_id: string;
  status: string;
  provider_id: string;
  provider_name: string;
  width: number;
  height: number;
  steps: number;
  guidance: number;
  tuning: GenerationTuning | null;
  warnings: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Stats {
  images: number;
  avg_rating: number;
  favorites: number;
  rated: number;
  jobs: number;
  feedback: number;
  storage_mb: number;
}

export interface LearningToken {
  token: string;
  lift: number;
  count: number;
  score: number;
}

export interface Insights {
  stage: string;
  summary: string;
  stats: Stats;
  feedback_samples: number;
  model: {
    name: string;
    samples: number;
    train_accuracy: number | null;
    cross_val_accuracy: number | null;
    trained_at: string | null;
    weights: number;
  } | null;
  quality: {
    average: number | null;
    recent_delta: number | null;
    trend: { id: string; date: string; quality: number; rating: number | null }[];
  };
  tokens: { positive: LearningToken[]; negative: LearningToken[] };
  styles: { style: string; count: number; avg_reward: number }[];
  providers: { provider_id: string; count: number; avg_reward: number }[];
  suggestion: GenerationTuning | null;
  adaptive_enabled: boolean;
  adaptive_prompt: boolean;
}

export interface InstallStatus {
  state: "idle" | "running" | "done" | "failed";
  variant: string | null;
  progress: number;
  message: string;
  tail: string[];
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
}

export interface RuntimeInfo {
  install: InstallStatus;
  local_engine: Availability;
  system: {
    cpu: { name: string; logical_cores: number };
    ram_gb: number | null;
    gpus: {
      vendor: string;
      name: string;
      total_mb: number;
      used_mb: number;
      free_mb: number;
      driver: string;
      temperature_c?: string;
      utilization?: string;
    }[];
    platform: string;
    python: string;
    python_executable: string;
    profile: {
      id: string;
      label: string;
      detail: string;
      suggested_long_edge: number;
      suggested_model: string;
    };
    npu_note: string;
  };
  hardware_profile: {
    id: string;
    label: string;
    detail: string;
    suggested_long_edge: number;
    suggested_model: string;
  };
  free_vram_mb: number | null;
  low_vram: {
    enabled: boolean;
    recommended: boolean;
    free_vram_mb: number | null;
    profile: RuntimeInfo["hardware_profile"];
  };
  python: string;
  python_version: string;
  data_dir: string;
  disk_free_gb: number | null;
  install_log: string;
  pip: string;
  stats?: Stats;
}

export interface Settings {
  default_provider_id: string;
  default_aspect: string;
  default_long_edge: number;
  default_steps: number | null;
  default_guidance: number | null;
  default_scheduler: string;
  auto_analyze: boolean;
  adaptive_enabled: boolean;
  adaptive_prompt: boolean;
  auto_tune_default: boolean;
  max_pixels: number;
  max_batch: number;
  local_engine: {
    device: string;
    dtype: string;
    cpu_offload: boolean;
    low_vram?: boolean;
    unload_after_generate?: boolean;
    model: string;
    hf_endpoint: string;
    local_files_only: boolean;
  };
  assistant?: AssistantConfig;
  comfyui: { timeout: number; sampler: string; scheduler: string };
  privacy: { strip_png_metadata: boolean; keep_init_uploads: boolean };
  ui: { reduce_motion: boolean; gallery_columns: number };
}

export interface AssistantConfig {
  enabled: boolean;
  base_url: string;
  model: string;
  timeout: number;
  has_key: boolean;
  key_masked: string;
}

export interface UpdateEvent {
  status: "checking" | "available" | "not-available" | "downloading" | "downloaded" | "error";
  version?: string;
  progress?: number;
  transferred?: number;
  total?: number;
  message?: string;
}

export interface RuntimeConfig {
  api: string;
  token: string;
  version: string;
  dataDir: string;
  resourcesDir: string;
  isPackaged: boolean;
  platform?: string;
}
