import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  Cloud,
  Cpu,
  Dices,
  Download,
  Heart,
  ImagePlus,
  Images,
  Layers,
  Loader2,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "../api";
import { Field, Segmented, Spinner, StarRating, Toggle } from "../components/Controls";
import { computeSize } from "../lib/dimensions";
import { cn, errorMessage, formatMs, formatVram, ratioLabel, truncate } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { GeneratePayload, Job, PageId, StudioImage } from "../types";

const EXAMPLES = [
  "雨夜的东京小巷，霓虹倒映在积水中，电影感广角镜头",
  "A lone astronaut in a bioluminescent forest, volumetric light, 35mm photograph",
  "极简产品摄影：磨砂玻璃香水瓶，暖色晨光，柔和阴影",
];

const LONG_EDGES = [512, 640, 768, 896, 1024, 1152, 1280, 1536, 2048];

interface InitImage {
  dataUrl: string;
  name: string;
  imageId?: string;
}

export function CreatePage({ active, onNavigate }: { active: boolean; onNavigate: (page: PageId) => void }) {
  const { runtime, settings, providers, presets, notify, fail, bumpGallery, galleryVersion } = useStudio();
  const [mode, setMode] = useState<"txt2img" | "img2img">("txt2img");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [providerId, setProviderId] = useState("");
  const [model, setModel] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [style, setStyle] = useState("cinematic");
  const [aspect, setAspect] = useState("1:1");
  const [longEdge, setLongEdge] = useState(1024);
  const [steps, setSteps] = useState("");
  const [guidance, setGuidance] = useState("");
  const [seed, setSeed] = useState("-1");
  const [scheduler, setScheduler] = useState("auto");
  const [strength, setStrength] = useState(0.55);
  const [batch, setBatch] = useState(1);
  const [autoTune, setAutoTune] = useState(true);
  const [enhancePrompt, setEnhancePrompt] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [initImage, setInitImage] = useState<InitImage | null>(null);
  const [dragging, setDragging] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [recent, setRecent] = useState<StudioImage[]>([]);
  const [promptBusy, setPromptBusy] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const appliedSettings = useRef(false);
  const appliedLowVram = useRef(false);

  const enabledProviders = useMemo(() => providers.filter((provider) => provider.enabled), [providers]);
  const provider = enabledProviders.find((item) => item.id === providerId) ?? enabledProviders[0];

  useEffect(() => {
    if (!settings || appliedSettings.current) return;
    appliedSettings.current = true;
    setLongEdge(settings.default_long_edge);
    setAspect(settings.default_aspect);
    setAutoTune(settings.auto_tune_default);
    setScheduler(settings.default_scheduler);
    setBatch(1);
  }, [settings]);

  useEffect(() => {
    if (appliedLowVram.current || !runtime) return;
    const free = runtime.free_vram_mb;
    if (free === null || free >= 2800) return;
    appliedLowVram.current = true;
    setLongEdge(512);
    setBatch(1);
    if (provider?.kind === "diffusers") setModel("stabilityai/sd-turbo");
  }, [runtime, provider]);

  useEffect(() => {
    if (!enabledProviders.length || providerId) return;
    const preferred =
      enabledProviders.find((item) => item.id === settings?.default_provider_id && item.availability.available) ??
      enabledProviders.find((item) => item.availability.available) ??
      enabledProviders[0];
    setProviderId(preferred.id);
  }, [enabledProviders, providerId, settings?.default_provider_id]);

  useEffect(() => {
    if (!provider) return;
    const fallback =
      provider.kind === "diffusers"
        ? provider.model || settings?.local_engine.model || "stabilityai/sd-turbo"
        : provider.model;
    setModel((current) => (current && providerId ? current : fallback || ""));
    const catalog = provider.model_catalog?.map((item) => item.id) ?? [];
    if (catalog.length) setModelOptions(catalog);
    else if (provider.kind === "diffusers") {
      setModelOptions([provider.model, "stabilityai/sd-turbo", "stabilityai/stable-diffusion-xl-base-1.0"].filter(Boolean));
    } else {
      setModelOptions(provider.model ? [provider.model] : []);
      void api
        .providerModels(provider.id)
        .then((result) => setModelOptions(result.models.length ? result.models : provider.model ? [provider.model] : []))
        .catch(() => setModelOptions(provider.model ? [provider.model] : []));
    }
  }, [provider, providerId, settings?.local_engine.model]);

  useEffect(() => {
    if (!active) return;
    void api
      .images({ limit: 4, sort: "newest" })
      .then((result) => setRecent(result.items))
      .catch(() => setRecent([]));
  }, [active, galleryVersion]);

  useEffect(() => {
    if (!active) return;
    const handler = (event: Event) => {
      const image = (event as CustomEvent<StudioImage>).detail;
      if (!image) return;
      setPrompt(image.prompt);
      setNegativePrompt(image.negative_prompt || "");
      setStyle(image.style || "cinematic");
      setAspect(ratioLabel(image.width, image.height));
      setLongEdge(Math.max(image.width, image.height));
      setSteps(String(image.steps || ""));
      setGuidance(String(image.guidance ?? ""));
      setSeed(String(image.seed ?? -1));
      setScheduler(image.scheduler || "auto");
      const nextMode = image.mode === "img2img" || image.mode === "crop" ? "img2img" : "txt2img";
      const knownProvider = providers.some((item) => item.id === image.provider_id);
      setMode(nextMode);
      setProviderId(knownProvider ? image.provider_id : "");
      setModel(knownProvider ? image.model : "");
      if (nextMode === "img2img") {
        setInitImage({ dataUrl: api.imageUrl(image, true), name: `参考 · ${image.id.slice(0, 8)}`, imageId: image.id });
      } else {
        setInitImage(null);
      }
      notify("已载入作品参数");
    };
    window.addEventListener("lumen:reuse", handler);
    return () => window.removeEventListener("lumen:reuse", handler);
  }, [active, notify, providers]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer = 0;

    const poll = async () => {
      try {
        const next = await api.job(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "succeeded") {
          setJobId(null);
          setSelectedIndex(0);
          setSubmitting(false);
          bumpGallery();
          notify("作品已完成", next.result?.tuning ? "本地偏好模型已参与本次参数选择" : undefined);
          return;
        }
        if (next.status === "failed") {
          setJobId(null);
          setSubmitting(false);
          fail(new ApiError(next.error?.message || "生成失败", 0, next.error?.code, next.error?.hint), "生成失败");
          return;
        }
        if (next.status === "cancelled") {
          setJobId(null);
          setSubmitting(false);
          notify("任务已取消");
          return;
        }
        timer = window.setTimeout(poll, 850);
      } catch (error) {
        if (cancelled) return;
        setJobId(null);
        setSubmitting(false);
        fail(error, "无法获取任务进度");
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [jobId, bumpGallery, notify, fail]);

  const size = useMemo(
    () => computeSize(aspect, longEdge, settings?.max_pixels ?? 4_194_304),
    [aspect, longEdge, settings?.max_pixels],
  );
  const images = job?.result?.images ?? [];
  const current = images[selectedIndex] ?? images[0] ?? null;
  const progress = job?.progress ?? 0;
  const running = Boolean(jobId) || (job?.status === "queued" || job?.status === "running");
  const freeVram = runtime?.low_vram?.free_vram_mb ?? null;
  const lowVram = freeVram !== null && freeVram < 4096;
  const providerReady = Boolean(provider?.availability.available);
  const cloud = provider?.kind === "openai" || provider?.kind === "stability";

  const handleFile = useCallback(
    (file: File) => {
      if (!file.type.startsWith("image/")) {
        fail(new Error("请选择图片文件"), "参考图无效");
        return;
      }
      if (file.size > 25 * 1024 * 1024) {
        fail(new Error("图片不能超过 25 MB"), "参考图过大");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => setInitImage({ dataUrl: String(reader.result), name: file.name });
      reader.onerror = () => fail(reader.error, "读取参考图失败");
      reader.readAsDataURL(file);
    },
    [fail],
  );

  const pickImage = async () => {
    if (window.lumen) {
      try {
        const picked = await window.lumen.pickImage();
        if (picked) setInitImage({ dataUrl: picked.dataUrl, name: picked.name });
      } catch (error) {
        fail(error, "无法选择图片");
      }
    } else {
      fileInput.current?.click();
    }
  };

  const enhance = async () => {
    if (!prompt.trim()) {
      notify("先写下画面想法，再让 Lumen 完善");
      return;
    }
    setPromptBusy(true);
    try {
      const result = await api.enhancePrompt(prompt, style);
      setPrompt(result.prompt);
      notify("提示词已完善", result.learned_tokens.length ? `融入了 ${result.learned_tokens.length} 个学习片段` : undefined);
    } catch (error) {
      fail(error, "完善提示词失败");
    } finally {
      setPromptBusy(false);
    }
  };

  const submit = async () => {
    if (!provider || !providerReady) {
      fail(new Error(provider?.availability.reason || "请先配置可用的模型引擎"), "无法开始生成");
      return;
    }
    if (!prompt.trim()) {
      notify("先描述你想看到的画面");
      return;
    }
    if (mode === "img2img" && !initImage) {
      fail(new Error("图生图需要一张参考图片"), "缺少参考图");
      return;
    }
    setSubmitting(true);
    setJob(null);
    try {
      const payload: GeneratePayload = {
        prompt: prompt.trim(),
        negative_prompt: negativePrompt.trim(),
        mode,
        provider_id: provider.id,
        model: model.trim() || provider.model,
        aspect_ratio: aspect,
        long_edge: longEdge,
        steps: steps.trim() ? Number(steps) : null,
        guidance: guidance.trim() ? Number(guidance) : null,
        seed: seed.trim() ? Number(seed) : -1,
        strength,
        batch_size: batch,
        scheduler,
        style,
        auto_tune: autoTune,
        enhance_prompt: enhancePrompt,
      };
      if (mode === "img2img" && initImage) {
        if (initImage.imageId) payload.init_image_id = initImage.imageId;
        else payload.init_image = initImage.dataUrl;
      }
      const result = await api.generate(payload);
      setJobId(result.job_id);
    } catch (error) {
      setSubmitting(false);
      const apiError = error instanceof ApiError ? error : null;
      fail(
        new Error(apiError?.hint ? `${errorMessage(error)} · ${apiError.hint}` : errorMessage(error)),
        "无法开始生成",
      );
    }
  };

  const cancel = async () => {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
      notify("已请求取消任务");
    } catch (error) {
      fail(error, "取消失败");
    }
  };

  const toggleFavorite = async () => {
    if (!current || favoriteBusy) return;
    setFavoriteBusy(true);
    try {
      const next = await api.feedback(current.id, { favorite: !current.favorite });
      setJob((value) =>
        value?.result
          ? {
              ...value,
              result: {
                ...value.result,
                images: value.result.images.map((image) => (image.id === current.id ? next.image : image)),
              },
            }
          : value,
      );
      bumpGallery();
      notify(next.image.favorite ? "已加入收藏" : "已取消收藏");
    } catch (error) {
      fail(error, "更新收藏失败");
    } finally {
      setFavoriteBusy(false);
    }
  };

  const rate = async (value: number) => {
    if (!current) return;
    try {
      const next = await api.feedback(current.id, { rating: value });
      setJob((jobValue) =>
        jobValue?.result
          ? {
              ...jobValue,
              result: {
                ...jobValue.result,
                images: jobValue.result.images.map((image) => (image.id === current.id ? next.image : image)),
              },
            }
          : jobValue,
      );
      bumpGallery();
      notify(`已记录 ${value} 星反馈`, "下一轮参数推荐会参考这次评价");
    } catch (error) {
      fail(error, "记录评分失败");
    }
  };

  const reuse = () => {
    if (!current) return;
    window.dispatchEvent(new CustomEvent("lumen:reuse", { detail: { ...current, mode: "txt2img" } }));
  };

  const useAsReference = (image: StudioImage) => {
    setMode("img2img");
    setInitImage({ dataUrl: api.imageUrl(image, true), name: `参考 · ${image.id.slice(0, 8)}`, imageId: image.id });
    setPrompt((value) => value || image.prompt);
    notify("已设为参考图");
  };

  const applyPromptExample = (value: string) => {
    setPrompt(value);
  };

  const reset = () => {
    setPrompt("");
    setNegativePrompt("");
    setInitImage(null);
    setSteps("");
    setGuidance("");
    setSeed("-1");
    setBatch(1);
    setAdvanced(false);
    setJob(null);
    setJobId(null);
  };

  return (
    <div className="create-page">
      <section className="composer">
        <div className="composer-head">
          <div>
            <span className="eyebrow">CREATE / 创作台</span>
            <h1>把想象变成画面</h1>
          </div>
          <button className="icon-button subtle" onClick={reset} title="重置参数">
            <RefreshCw size={16} />
          </button>
        </div>

        <Segmented
          value={mode}
          onChange={(value) => setMode(value)}
          options={[
            { value: "txt2img", label: "文生图", icon: <Sparkles size={15} /> },
            { value: "img2img", label: "图生图", icon: <ImagePlus size={15} /> },
          ]}
        />

        {mode === "img2img" && (
          <div
            className={cn("upload-zone", dragging && "dragging", initImage && "has-image")}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files[0];
              if (file) handleFile(file);
            }}
            onClick={() => !initImage && void pickImage()}
          >
            {initImage ? (
              <>
                <img src={initImage.dataUrl} alt="参考图预览" />
                <div className="upload-overlay">
                  <span>{truncate(initImage.name, 28)}</span>
                  <div className="upload-actions">
                    <button
                      className="icon-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void pickImage();
                      }}
                      title="更换参考图"
                    >
                      <RefreshCw size={14} />
                    </button>
                    <button
                      className="icon-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setInitImage(null);
                      }}
                      title="移除参考图"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <span className="upload-icon">
                  <ImagePlus size={20} />
                </span>
                <div>
                  <strong>拖入参考图，或点击选择</strong>
                  <small>PNG / JPG / WEBP · 最大 25 MB · 图片只在本地处理</small>
                </div>
              </>
            )}
          </div>
        )}

        <div className="prompt-shell">
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={mode === "img2img" ? "描述希望如何改变这张图片…" : "描述主体、光线、材质、镜头与氛围…"}
            maxLength={3000}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <div className="prompt-toolbar">
            <button className="prompt-enhance" onClick={() => void enhance()} disabled={promptBusy}>
              {promptBusy ? <Spinner size={13} /> : <Wand2 size={14} />}
              帮我完善
            </button>
            <span className="char-count">{prompt.length} / 3000</span>
          </div>
        </div>
        <div className="example-row">
          {EXAMPLES.map((example) => (
            <button key={example} className="example-chip" onClick={() => applyPromptExample(example)}>
              {truncate(example, 24)}
            </button>
          ))}
        </div>

        <div className="model-row">
          <label className="select-field">
            <span>引擎</span>
            <select
              value={provider?.id ?? ""}
              onChange={(event) => {
                setProviderId(event.target.value);
                setModel("");
              }}
            >
              {enabledProviders.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} {item.availability.available ? "" : "（不可用）"}
                </option>
              ))}
            </select>
            <ChevronDown size={13} className="select-caret" />
          </label>
          <label className="select-field model-field">
            <span>模型</span>
            <input
              value={model}
              list="lumen-model-options"
              placeholder="模型 ID 或本地路径"
              onChange={(event) => setModel(event.target.value)}
            />
            <datalist id="lumen-model-options">
              {modelOptions.map((option) => (
                <option value={option} key={option} />
              ))}
            </datalist>
          </label>
          <span className={cn("provider-kind", cloud ? "cloud" : provider?.kind === "demo" ? "demo" : "local")}>
            {cloud ? <Cloud size={12} /> : provider?.kind === "demo" ? <Zap size={12} /> : <Cpu size={12} />}
            {provider?.kind === "diffusers" ? "本地" : provider?.kind === "comfyui" ? "局域网" : provider?.kind === "demo" ? "示例" : "云端"}
          </span>
        </div>

        {!providerReady && provider && (
          <div className="inline-alert warn">
            <AlertTriangle size={16} />
            <div>
              <strong>{provider.availability.reason}</strong>
              <span>{provider.availability.detail}</span>
            </div>
            <button className="text-button" onClick={() => onNavigate("models")}>
              去配置 <ArrowRight size={13} />
            </button>
          </div>
        )}

        {lowVram && provider?.kind === "diffusers" && (
          <div className="inline-alert info">
            <Cpu size={15} />
            <div>
              <strong>低显存守护已开启</strong>
              <span>
                当前约 {formatVram(freeVram)} 可用 · 顺序卸载 / VAE 分块 · 生成后自动释放
              </span>
            </div>
            <button className="text-button" onClick={() => onNavigate("models")}>
              详情
            </button>
          </div>
        )}

        <div className="control-section">
          <div className="section-head">
            <span className="section-title">画面风格</span>
            <span className="section-meta">STYLE</span>
          </div>
          <div className="style-grid">
            {(presets?.styles ?? []).map((item) => (
              <button
                key={item.id}
                className={cn("style-chip", style === item.id && "active")}
                onClick={() => setStyle(item.id)}
                style={{ "--style-accent": item.accent } as CSSProperties}
              >
                <span className="style-dot" />
                {item.label}
                {style === item.id && <Check size={12} className="style-check" />}
              </button>
            ))}
          </div>
        </div>

        <div className="control-section">
          <div className="section-head">
            <span className="section-title">画幅比例</span>
            <span className="section-meta">
              {size.width} × {size.height} · {size.megapixels} MP
            </span>
          </div>
          <div className="aspect-grid">
            {(presets?.aspects ?? []).map((item) => {
              const ratio = Number(item.ratio);
              const width = ratio >= 1 ? 26 : Math.max(9, Math.round(26 * ratio));
              const height = ratio >= 1 ? Math.max(9, Math.round(26 / ratio)) : 26;
              return (
                <button
                  key={item.id}
                  className={cn("aspect-chip", aspect === item.id && "active")}
                  onClick={() => setAspect(item.id)}
                  title={item.hint}
                >
                  <span className="aspect-shape" style={{ width, height }} />
                  <span>{item.id}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="control-section">
          <div className="section-head">
            <span className="section-title">长边分辨率</span>
            <span className="section-meta">{longEdge}px</span>
          </div>
          <div className="edge-row">
            {LONG_EDGES.map((edge) => (
              <button
                key={edge}
                className={cn("edge-chip", longEdge === edge && "active")}
                onClick={() => setLongEdge(edge)}
              >
                {edge}
              </button>
            ))}
          </div>
          {longEdge > 1024 && lowVram && (
            <p className="control-hint warn-text">可用显存较低，建议 512–768；高分辨率可能变慢或显存不足。</p>
          )}
        </div>

        <div className="advanced-block">
          <button className="advanced-toggle" onClick={() => setAdvanced((value) => !value)}>
            <span>
              <SlidersHorizontal size={15} />
              高级参数
            </span>
            <span className="advanced-summary">
              {steps ? `${steps} 步` : "自动步数"} · {guidance ? `CFG ${guidance}` : "自动 CFG"} · 种子{" "}
              {seed === "-1" ? "随机" : seed}
            </span>
            <ChevronDown size={15} className={cn("chevron", advanced && "open")} />
          </button>
          {advanced && (
            <div className="advanced-panel">
              <div className="advanced-grid">
                <Field label="采样步数" hint="留空自动">
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={100}
                    value={steps}
                    placeholder="自动"
                    onChange={(event) => setSteps(event.target.value)}
                  />
                </Field>
                <Field label="引导强度 CFG" hint="留空自动">
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={30}
                    step={0.5}
                    value={guidance}
                    placeholder="自动"
                    onChange={(event) => setGuidance(event.target.value)}
                  />
                </Field>
                <Field label="采样器">
                  <select className="input" value={scheduler} onChange={(event) => setScheduler(event.target.value)}>
                    {(presets?.schedulers ?? [{ id: "auto", label: "自动" }]).map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="种子" hint="-1 为随机">
                  <div className="seed-row">
                    <input
                      className="input"
                      type="number"
                      value={seed}
                      onChange={(event) => setSeed(event.target.value)}
                    />
                    <button className="icon-button bordered" onClick={() => setSeed("-1")} title="随机种子">
                      <Dices size={15} />
                    </button>
                  </div>
                </Field>
                <Field label="生成数量" hint="最多 4 张">
                  <select className="input" value={batch} onChange={(event) => setBatch(Number(event.target.value))}>
                    {[1, 2, 3, 4].map((value) => (
                      <option value={value} key={value}>
                        {value} 张
                      </option>
                    ))}
                  </select>
                </Field>
                {mode === "img2img" && (
                  <Field label="重绘强度" hint={`${Math.round(strength * 100)}%`}>
                    <input
                      type="range"
                      min={0.1}
                      max={1}
                      step={0.05}
                      value={strength}
                      onChange={(event) => setStrength(Number(event.target.value))}
                    />
                  </Field>
                )}
              </div>
              <Field label="负面提示词" hint="不希望出现的元素">
                <textarea
                  className="input textarea-small"
                  value={negativePrompt}
                  onChange={(event) => setNegativePrompt(event.target.value)}
                  placeholder="blurry, low quality, watermark, distorted hands…"
                  rows={2}
                />
              </Field>
              <div className="advanced-switches">
                <div className="switch-row">
                  <div>
                    <strong>本地偏好调参</strong>
                    <span>用已评分作品学习步数、CFG 与采样器</span>
                  </div>
                  <Toggle checked={autoTune} onChange={setAutoTune} label="本地偏好调参" />
                </div>
                <div className="switch-row">
                  <div>
                    <strong>提示词增强</strong>
                    <span>补充构图、光线与细节描述</span>
                  </div>
                  <Toggle checked={enhancePrompt} onChange={setEnhancePrompt} label="提示词增强" />
                </div>
              </div>
            </div>
          )}
        </div>

        <button
          className={cn("generate-button", (!providerReady || running) && "disabled")}
          onClick={() => void submit()}
          disabled={!providerReady || running || submitting}
        >
          {running || submitting ? <Loader2 size={18} className="spin" /> : <Sparkles size={18} />}
          <span>{running ? "正在生成…" : provider?.kind === "demo" ? "生成示例画面" : "开始生成"}</span>
          <kbd>Ctrl ↵</kbd>
        </button>

        {(running || job?.status === "failed") && (
          <div className={cn("job-card", job?.status === "failed" && "failed")}>
            <div className="job-top">
              <div>
                <span className="job-stage">{job?.stage || "已加入队列"}</span>
                <strong>{job?.status === "failed" ? "生成未完成" : `${Math.round(progress * 100)}%`}</strong>
              </div>
              {running && (
                <button className="text-button danger" onClick={() => void cancel()}>
                  <X size={13} /> 取消
                </button>
              )}
            </div>
            <div className="progress-track">
              <span style={{ width: `${Math.max(4, progress * 100)}%` }} />
            </div>
            {job?.queue_position ? <p className="job-note">前面还有 {job.queue_position - 1} 个任务</p> : null}
          </div>
        )}
      </section>

      <section className="stage-panel">
        <div className="stage-head">
          <div>
            <span className="eyebrow">OUTPUT / 输出</span>
            <h2>{current ? "本次作品" : running ? "正在显影" : "画面会出现在这里"}</h2>
          </div>
          <div className="stage-head-actions">
            {current && (
              <span className="stage-badge">
                <Layers size={13} />
                {current.width} × {current.height}
              </span>
            )}
            {current && (
              <button className="icon-button bordered" onClick={() => void toggleFavorite()} title="收藏">
                <Heart size={16} fill={current.favorite ? "currentColor" : "none"} className={current.favorite ? "liked" : ""} />
              </button>
            )}
            {current && (
              <a
                className="icon-button bordered"
                href={api.mediaUrl(current.file_url, { download: true })}
                download
                title="下载 PNG"
              >
                <Download size={16} />
              </a>
            )}
          </div>
        </div>

        <div className={cn("stage-canvas", current && "has-result", running && "is-running")}>
          {running || submitting ? (
            <div className="stage-progress">
              <div className="orbit" style={{ "--progress": progress } as CSSProperties}>
                <div className="orbit-inner">
                  <strong>{Math.round(progress * 100)}</strong>
                  <span>%</span>
                </div>
              </div>
              <h3>{job?.stage || "正在唤醒本地引擎"}</h3>
              <p>
                {provider?.name} · {model || "默认模型"}
              </p>
              <div className="progress-track wide">
                <span style={{ width: `${Math.max(3, progress * 100)}%` }} />
              </div>
              <p className="stage-progress-note">
                {freeVram !== null ? `可用显存 ${formatVram(freeVram)}` : "CPU 模式"} · 关闭窗口会中断任务
              </p>
            </div>
          ) : current ? (
            <>
              <div className="stage-image-wrap">
                <img src={api.imageUrl(current)} alt={current.prompt} />
                <div className="stage-image-shade" />
                <div className="stage-image-meta">
                  <span>{current.provider_name}</span>
                  <span>{truncate(current.model || "本地模型", 28)}</span>
                  {current.params && (current.params as Record<string, unknown>).low_vram ? (
                    <span className="vram-chip">
                      <Cpu size={11} /> 低显存模式
                    </span>
                  ) : null}
                </div>
              </div>
              {images.length > 1 && (
                <div className="batch-strip">
                  {images.map((image, index) => (
                    <button
                      key={image.id}
                      className={cn("batch-thumb", selectedIndex === index && "active")}
                      onClick={() => setSelectedIndex(index)}
                    >
                      <img src={api.imageUrl(image, true)} alt={`第 ${index + 1} 张`} />
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : job?.status === "failed" ? (
            <div className="stage-empty error">
              <AlertTriangle size={26} />
              <h3>这次没有画出来</h3>
              <p>{job.error?.message}</p>
              {job.error?.hint && <p className="stage-hint">{job.error.hint}</p>}
              <button className="button button-ghost" onClick={() => onNavigate("models")}>
                检查模型设置
              </button>
            </div>
          ) : (
            <div className="stage-empty">
              <div className="stage-grid" />
              <div className="stage-empty-mark">
                <Sparkles size={28} />
              </div>
              <h3>从一句话开始</h3>
              <p>写下主体、光线与氛围。Lumen 会把提示词、尺寸与参数一起交给本地或云端引擎。</p>
              <div className="stage-features">
                <span>
                  <Check size={12} /> 文生图
                </span>
                <span>
                  <Check size={12} /> 图生图
                </span>
                <span>
                  <Check size={12} /> 本地优先
                </span>
              </div>
              {recent.length > 0 && (
                <div className="recent-strip">
                  <div className="recent-head">
                    <span>最近作品</span>
                    <button className="text-button" onClick={() => onNavigate("gallery")}>
                      全部 <ArrowRight size={12} />
                    </button>
                  </div>
                  <div className="recent-grid">
                    {recent.map((image) => (
                      <button
                        key={image.id}
                        className="recent-thumb"
                        onClick={() => useAsReference(image)}
                        title="用作图生图参考"
                      >
                        <img src={api.imageUrl(image, true)} alt={image.prompt} />
                        <span>
                          <ImagePlus size={13} /> 参考
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {provider?.kind === "demo" && (
                <div className="demo-note">
                  <Zap size={14} />
                  当前是离线示例引擎。安装本地运行时后即可用 RTX 显卡真实生成。
                  <button className="text-button" onClick={() => onNavigate("models")}>
                    配置
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {current && (
          <div className="stage-details">
            <div className="detail-top">
              <div className="detail-rating">
                <span>喜欢这张吗？</span>
                <StarRating value={current.rating} onChange={(value) => void rate(value)} />
              </div>
              <div className="detail-actions">
                <button className="button button-small button-ghost" onClick={reuse}>
                  <RefreshCw size={13} /> 复用参数
                </button>
                <button className="button button-small button-ghost" onClick={() => onNavigate("gallery")}>
                  <Images size={13} /> 作品库
                </button>
              </div>
            </div>
            <div className="meta-grid">
              <div>
                <span>尺寸</span>
                <strong>
                  {current.width} × {current.height}
                </strong>
              </div>
              <div>
                <span>步数 / CFG</span>
                <strong>
                  {current.steps} / {current.guidance}
                </strong>
              </div>
              <div>
                <span>采样器</span>
                <strong>{current.scheduler}</strong>
              </div>
              <div>
                <span>种子</span>
                <strong>{current.seed}</strong>
              </div>
              <div>
                <span>耗时</span>
                <strong>{formatMs(current.generation_ms)}</strong>
              </div>
              <div>
                <span>画质分析</span>
                <strong>{current.analysis.technical_score ?? "—"} / 100</strong>
              </div>
            </div>
            <div className="stage-prompt">
              <span>提示词</span>
              <p>{current.prompt}</p>
            </div>
            {job?.result?.tuning && (
              <div className="tuning-card">
                <span className="tuning-icon">
                  <Sparkles size={14} />
                </span>
                <div>
                  <strong>本地偏好模型参与了本次调参</strong>
                  <p>
                    {job.result.tuning.reason} · 置信度 {Math.round(job.result.tuning.confidence * 100)}% · 样本{" "}
                    {job.result.tuning.samples}
                  </p>
                </div>
              </div>
            )}
            {job?.result?.warnings?.length ? (
              <div className="warning-list">
                {job.result.warnings.map((warning) => (
                  <span key={warning}>
                    <AlertTriangle size={11} /> {warning}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
