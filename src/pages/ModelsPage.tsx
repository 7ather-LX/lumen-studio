import {
  AlertTriangle,
  Check,
  ChevronDown,
  Cloud,
  Cpu,
  Download,
  FolderOpen,
  Gauge,
  HardDrive,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Field, Spinner, Toggle } from "../components/Controls";
import { Modal } from "../components/Modal";
import { cn, formatVram } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { LocalModel, PageId, Provider, ProviderDraft } from "../types";

const KIND_ICON = {
  diffusers: Cpu,
  comfyui: Server,
  openai: Cloud,
  stability: Cloud,
  demo: Zap,
};

const KIND_HINT: Record<Provider["kind"], string> = {
  diffusers: "内置 PyTorch + Diffusers，直接调用本机显卡。按需下载模型，生成后自动释放。",
  comfyui: "连接本机或局域网 ComfyUI，复用任意 checkpoint、LoRA 与自定义节点。",
  openai: "OpenAI Images 或任意 OpenAI 兼容图片端点，需要网络与 API Key。",
  stability: "Stability AI 官方 API，支持文生图与 SD3 图生图。",
  demo: "完全离线的算法示例，不需要模型，用于预览界面与测试工作流。",
};

type DraftState = ProviderDraft & { rawOptions: string };

function newDraft(kind: Provider["kind"] = "diffusers"): DraftState {
  const base: Record<Provider["kind"], Partial<ProviderDraft>> = {
    diffusers: {
      name: "本地 Diffusers",
      base_url: "",
      model: "stabilityai/sd-turbo",
      options: { device: "auto", dtype: "auto", cpu_offload: true, allow_download: true },
    },
    comfyui: { name: "ComfyUI", base_url: "http://127.0.0.1:8188", model: "", options: { timeout: 420 } },
    openai: { name: "OpenAI Images", base_url: "https://api.openai.com/v1", model: "gpt-image-1", options: {} },
    stability: { name: "Stability AI", base_url: "https://api.stability.ai", model: "sd3.5-large", options: {} },
    demo: { name: "离线示例引擎", base_url: "", model: "lumen-demo-v1", options: {} },
  };
  return {
    name: base[kind].name ?? "",
    kind,
    base_url: base[kind].base_url ?? "",
    model: base[kind].model ?? "",
    enabled: true,
    options: base[kind].options ?? {},
    rawOptions: JSON.stringify(base[kind].options ?? {}, null, 2),
  };
}

export function ModelsPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const {
    runtime,
    settings,
    providers,
    presets,
    refreshRuntime,
    refreshProviders,
    refreshSettings,
    notify,
    fail,
  } = useStudio();
  const [editing, setEditing] = useState<DraftState | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [variant, setVariant] = useState<"auto" | "cuda" | "cpu">("auto");
  const [models, setModels] = useState<{ id: string; size_gb: number }[]>([]);
  const [showTiers, setShowTiers] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [showLog, setShowLog] = useState(false);

  const localProvider = providers.find((provider) => provider.kind === "diffusers");
  const localReady = runtime?.local_engine.available ?? false;
  const install = runtime?.install;
  const gpu = runtime?.system.gpus[0];
  const free = runtime?.free_vram_mb ?? null;
  const profile = runtime?.hardware_profile;
  const lowVramEnabled = Boolean(settings?.local_engine.low_vram ?? true);
  const cuda = gpu?.vendor === "NVIDIA";

  useEffect(() => {
    void api
      .localModels()
      .then((result) => setModels(result.models))
      .catch(() => setModels([]));
  }, [runtime?.install.state]);

  useEffect(() => {
    if (install?.state !== "running") return;
    const timer = window.setInterval(() => void refreshRuntime(), 1600);
    return () => window.clearInterval(timer);
  }, [install?.state, refreshRuntime]);

  const updateLowVram = async (value: boolean) => {
    if (!settings) return;
    try {
      await api.updateSettings({ local_engine: { ...settings.local_engine, low_vram: value, unload_after_generate: value } });
      await refreshSettings();
      await refreshRuntime();
      notify(value ? "低显存守护已开启" : "已关闭低显存守护", value ? "生成后会释放模型与显存缓存" : "模型会尽量驻留显存");
    } catch (error) {
      fail(error, "无法更新低显存设置");
    }
  };

  const startInstall = async () => {
    const size = variant === "cpu" ? "约 1.5 GB" : "约 3–6 GB";
    if (!window.confirm(`将下载 PyTorch 与 Diffusers 本地运行时（${size}）。安装期间请保持网络连接，是否继续？`)) return;
    setInstalling(true);
    try {
      const result = await api.installRuntime(variant);
      notify(result.message);
      await refreshRuntime();
    } catch (error) {
      fail(error, "无法开始安装");
    } finally {
      setInstalling(false);
    }
  };

  const cancelInstall = async () => {
    try {
      const result = await api.cancelRuntimeInstall();
      notify(result.message);
      await refreshRuntime();
    } catch (error) {
      fail(error, "取消安装失败");
    }
  };

  const testProvider = async (provider: Provider) => {
    setTestingId(provider.id);
    try {
      const result = await api.testProvider(provider.id);
      if (result.ok) notify("连接成功", result.detail || result.message);
      else fail(new Error(result.detail || result.message), "连接失败");
    } catch (error) {
      fail(error, "连接测试失败");
    } finally {
      setTestingId(null);
    }
  };

  const setDefault = async (provider: Provider) => {
    try {
      await api.setDefaultProvider(provider.id);
      await refreshProviders();
      await refreshSettings();
      notify(`${provider.name} 已设为默认引擎`);
    } catch (error) {
      fail(error, "设置默认引擎失败");
    }
  };

  const removeProvider = async (provider: Provider) => {
    if (!window.confirm(`删除「${provider.name}」的配置？已生成的作品不会受影响。`)) return;
    try {
      await api.deleteProvider(provider.id);
      await refreshProviders();
      notify("供应商已删除");
    } catch (error) {
      fail(error, "删除失败");
    }
  };

  const openEdit = (provider?: Provider) => {
    if (!provider) {
      setEditing(newDraft("diffusers"));
      return;
    }
    setEditing({
      id: provider.id,
      name: provider.name,
      kind: provider.kind,
      base_url: provider.base_url,
      model: provider.model,
      enabled: provider.enabled,
      is_default: provider.is_default,
      options: provider.options,
      rawOptions: JSON.stringify(provider.options, null, 2),
    });
    setModelOptions([provider.model].filter(Boolean));
  };

  const updateDraft = (patch: Partial<DraftState>) =>
    setEditing((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      if (patch.options && patch.rawOptions === undefined) next.rawOptions = JSON.stringify(patch.options, null, 2);
      return next;
    });

  const saveDraft = async () => {
    if (!editing) return;
    if (!editing.name.trim()) {
      fail(new Error("请填写名称"), "无法保存");
      return;
    }
    setSaving(true);
    try {
      let options = editing.options;
      if (editing.rawOptions.trim()) {
        try {
          options = JSON.parse(editing.rawOptions);
        } catch {
          throw new Error("高级参数不是有效的 JSON");
        }
      }
      await api.saveProvider({
        id: editing.id,
        name: editing.name.trim(),
        kind: editing.kind,
        base_url: editing.base_url.trim(),
        model: editing.model.trim(),
        enabled: editing.enabled,
        options,
        api_key: editing.api_key?.trim() || undefined,
        clear_secret: editing.clear_secret,
      });
      await refreshProviders();
      await refreshSettings();
      setEditing(null);
      notify("供应商配置已保存");
    } catch (error) {
      fail(error, "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const fetchModels = async () => {
    if (!editing?.id) return;
    setModelLoading(true);
    try {
      const result = await api.providerModels(editing.id);
      setModelOptions(result.models);
      if (result.models.length === 1 && !editing.model) updateDraft({ model: result.models[0] });
      notify(result.models.length ? `找到 ${result.models.length} 个模型` : "没有发现模型");
    } catch (error) {
      fail(error, "获取模型列表失败");
    } finally {
      setModelLoading(false);
    }
  };

  const applyRecommendedModel = async (model: LocalModel) => {
    if (!settings || !localProvider) return;
    try {
      await api.updateSettings({ local_engine: { ...settings.local_engine, model: model.id } });
      await api.saveProvider({
        id: localProvider.id,
        name: localProvider.name,
        kind: "diffusers",
        base_url: "",
        model: model.id,
        enabled: true,
        options: localProvider.options,
      });
      await Promise.all([refreshSettings(), refreshProviders()]);
      notify(`已选择 ${model.label}`, model.note);
    } catch (error) {
      fail(error, "选择模型失败");
    }
  };

  const activeModel = settings?.local_engine.model ?? localProvider?.model ?? "stabilityai/sd-turbo";
  const catalog = localProvider?.model_catalog ?? presets?.local_models ?? [];

  const vramPercent = useMemo(() => {
    if (!gpu?.total_mb) return 0;
    return Math.min(100, Math.round((gpu.used_mb / gpu.total_mb) * 100));
  }, [gpu]);

  return (
    <div className="page models-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">ENGINES / 模型引擎</span>
          <h1>选择画面的发动机</h1>
          <p>本地 Diffusers、ComfyUI 与云端 API 共用一套创作界面。本地推理不设生成次数限制，数据不出本机。</p>
        </div>
        <div className="header-actions">
          <button className="button button-ghost" onClick={() => onNavigate("create")}>
            去创作
          </button>
          <button className="button button-primary" onClick={() => openEdit()}>
            <Plus size={15} />
            添加供应商
          </button>
        </div>
      </header>

      <section className="hardware-card">
        <div className="hardware-main">
          <div className="hardware-title">
            <span className="hardware-icon">
              <Gauge size={20} />
            </span>
            <div>
              <span className="eyebrow">HARDWARE / 本机硬件</span>
              <h2>{gpu?.name ?? "CPU 推理模式"}</h2>
              <p>{profile?.detail ?? "未检测到独立显卡，仍可使用 CPU 或云端引擎。"}</p>
            </div>
          </div>
          <div className="hardware-stats">
            <div>
              <span>显存占用</span>
              <strong>
                {gpu ? `${formatVram(gpu.used_mb)} / ${formatVram(gpu.total_mb)}` : "共享内存"}
              </strong>
            </div>
            <div>
              <span>当前可用</span>
              <strong className={free !== null && free < 2000 ? "danger-text" : ""}>
                {free !== null ? formatVram(free) : "—"}
              </strong>
            </div>
            <div>
              <span>内存</span>
              <strong>{runtime?.system.ram_gb ? `${runtime.system.ram_gb} GB` : "—"}</strong>
            </div>
            <div>
              <span>CPU</span>
              <strong>{runtime?.system.cpu.logical_cores ?? "—"} 线程</strong>
            </div>
          </div>
          <div className="vram-meter">
            <span style={{ width: `${vramPercent}%` }} className={free !== null && free < 2000 ? "warn" : ""} />
          </div>
          <div className="vram-caption">
            <span>已用 {vramPercent}%</span>
            <span>{profile?.label}</span>
          </div>
        </div>
        <div className="hardware-side">
          <div className="low-vram-head">
            <div>
              <strong>低显存守护</strong>
              <span>与其他 AI 共用显卡时推荐开启</span>
            </div>
            <Toggle checked={lowVramEnabled} onChange={(value) => void updateLowVram(value)} label="低显存守护" />
          </div>
          <ul className="low-vram-list">
            <li>
              <Check size={13} /> 顺序 CPU 卸载，峰值显存更低
            </li>
            <li>
              <Check size={13} /> VAE 分块与注意力切片
            </li>
            <li>
              <Check size={13} /> 生成结束立即释放模型
            </li>
          </ul>
          <p className="hardware-note">
            界面本身占用约 100–200 MB 显存。若可用显存低于 2 GB，建议 SD-Turbo 512 或先关闭其他 AI 程序。
          </p>
          <button className="text-button" onClick={() => setShowTiers((value) => !value)}>
            查看推荐硬件配置 <ChevronDown size={13} className={cn(showTiers && "rotate")} />
          </button>
        </div>
        {showTiers && (
          <div className="tier-table">
            {(presets?.hardware.tiers ?? []).map((tier) => (
              <div className={cn("tier-row", tier.id === "recommended" && "highlight")} key={tier.id}>
                <div>
                  <strong>{tier.label}</strong>
                  {tier.id === "recommended" && <span className="tier-tag">推荐</span>}
                </div>
                <span>{tier.gpu}</span>
                <span>{tier.vram}</span>
                <span>{tier.ram} 内存</span>
                <p>{tier.experience}</p>
              </div>
            ))}
            <p className="tier-foot">NPU：可通过 ComfyUI 的 OpenVINO / DirectML 后端使用，内置 Diffusers 引擎默认选择 CUDA 或 CPU。</p>
          </div>
        )}
      </section>

      <section className="runtime-card">
        <div className="runtime-head">
          <div className="runtime-title">
            <span className={cn("runtime-dot", localReady ? "ok" : "idle")} />
            <div>
              <span className="eyebrow">LOCAL RUNTIME</span>
              <h2>{localReady ? "本地生成运行时已就绪" : "安装本地生成运行时"}</h2>
              <p>{localReady ? runtime?.local_engine.detail : "PyTorch + Diffusers，一次性安装，之后完全离线。"}</p>
            </div>
          </div>
          <div className="runtime-actions">
            {localReady ? (
              <span className="ready-badge">
                <ShieldCheck size={14} /> {runtime?.local_engine.version}
              </span>
            ) : install?.state === "running" ? (
              <button className="button button-ghost" onClick={() => void cancelInstall()}>
                取消安装
              </button>
            ) : (
              <>
                <select
                  className="input compact"
                  value={variant}
                  onChange={(event) => setVariant(event.target.value as "auto" | "cuda" | "cpu")}
                >
                  <option value="auto">自动选择</option>
                  {cuda && <option value="cuda">CUDA（NVIDIA）</option>}
                  <option value="cpu">CPU</option>
                </select>
                <button className="button button-primary" onClick={() => void startInstall()} disabled={installing}>
                  {installing ? <Loader2 size={15} className="spin" /> : <Download size={15} />}
                  安装本地引擎
                </button>
              </>
            )}
            <button className="icon-button bordered" onClick={() => void refreshRuntime()} title="刷新状态">
              <RefreshCw size={15} />
            </button>
          </div>
        </div>

        {install?.state === "running" && (
          <div className="install-progress">
            <div className="install-top">
              <span>{install.message}</span>
              <strong>{Math.round(install.progress * 100)}%</strong>
            </div>
            <div className="progress-track">
              <span style={{ width: `${Math.max(3, install.progress * 100)}%` }} />
            </div>
            <button className="text-button" onClick={() => setShowLog((value) => !value)}>
              {showLog ? "收起日志" : "查看安装日志"}
            </button>
            {showLog && <pre className="install-log">{install.tail.slice(-8).join("\n") || "等待下载…"}</pre>}
          </div>
        )}
        {install?.state === "failed" && (
          <div className="inline-alert warn">
            <AlertTriangle size={15} />
            <div>
              <strong>{install.message}</strong>
              <span>{install.tail.slice(-1)[0] || install.error || "查看日志定位问题"}</span>
            </div>
            <button
              className="text-button"
              onClick={() => {
                if (runtime?.install_log) void window.lumen?.openPath(runtime.install_log);
              }}
            >
              打开日志
            </button>
          </div>
        )}

        <div className="runtime-foot">
          <div>
            <HardDrive size={14} />
            <span>运行时：</span>
            <strong>Python {runtime?.python_version ?? "—"}</strong>
          </div>
          <div>
            <Download size={14} />
            <span>下载：</span>
            <strong>{activeModel}</strong>
          </div>
          <div>
            <FolderOpen size={14} />
            <span>数据目录：</span>
            <button className="text-button" onClick={() => runtime?.data_dir && void window.lumen?.openPath(runtime.data_dir)}>
              打开
            </button>
          </div>
          <div>
            <Sparkles size={14} />
            <span>磁盘剩余：</span>
            <strong>{runtime?.disk_free_gb ? `${runtime.disk_free_gb} GB` : "—"}</strong>
          </div>
        </div>

        {models.length > 0 && (
          <div className="cached-models">
            <span>已下载模型</span>
            {models.slice(0, 6).map((model) => (
              <span className="model-pill" key={model.id}>
                {model.id} · {model.size_gb} GB
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="model-recommend">
        <div className="section-head standalone">
          <div>
            <span className="section-title">本地模型建议</span>
            <span className="section-meta">按可用显存选择 · 首次生成时下载</span>
          </div>
          <span className="model-current">
            当前 <strong>{activeModel}</strong>
          </span>
        </div>
        <div className="model-catalog">
          {catalog.map((model) => (
            <button
              key={model.id}
              className={cn("model-card", activeModel === model.id && "active")}
              onClick={() => void applyRecommendedModel(model)}
            >
              <div className="model-card-head">
                <span className="model-family">{model.family}</span>
                {activeModel === model.id && <Check size={14} />}
              </div>
              <strong>{model.label}</strong>
              <p>{model.note}</p>
              <div className="model-card-meta">
                <span>{model.download_gb} GB</span>
                <span>最低 {formatVram(model.min_vram_mb)}</span>
                <span>{model.default_edge}px</span>
              </div>
              <small>{model.license}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="providers-section">
        <div className="section-head standalone">
          <div>
            <span className="section-title">供应商</span>
            <span className="section-meta">本地与云端共用同一界面</span>
          </div>
          <button className="button button-ghost button-small" onClick={() => openEdit()}>
            <Plus size={14} /> 添加
          </button>
        </div>
        <div className="provider-grid">
          {providers.map((provider) => {
            const Icon = KIND_ICON[provider.kind];
            return (
              <article className={cn("provider-card", provider.is_default && "default")} key={provider.id}>
                <div className="provider-card-head">
                  <span className={cn("provider-icon", provider.kind)}>
                    <Icon size={18} />
                  </span>
                  <div className="provider-title">
                    <strong>{provider.name}</strong>
                    <span>{provider.kind_label}</span>
                  </div>
                  <div className="provider-badges">
                    {provider.is_default && <span className="default-badge">默认</span>}
                    <span className={cn("availability-dot", provider.availability.available ? "ok" : "off")} />
                  </div>
                </div>
                <p className="provider-desc">{KIND_HINT[provider.kind]}</p>
                <div className="provider-detail">
                  <span>{provider.availability.reason}</span>
                  {provider.base_url && <small>{provider.base_url}</small>}
                  {provider.kind === "diffusers" && <small>{provider.model || activeModel}</small>}
                  {provider.kind === "comfyui" && <small>{provider.model || "自动选择 checkpoint"}</small>}
                  {provider.secret_set && (
                    <small className="secret-line">
                      <KeyRound size={11} /> {provider.secret_masked}
                    </small>
                  )}
                </div>
                <div className="provider-actions">
                  {!provider.is_default && provider.enabled && provider.availability.available && (
                    <button className="text-button" onClick={() => void setDefault(provider)}>
                      设为默认
                    </button>
                  )}
                  <button className="text-button" onClick={() => void testProvider(provider)} disabled={testingId === provider.id}>
                    {testingId === provider.id ? <Spinner size={12} /> : <RefreshCw size={12} />} 测试
                  </button>
                  <button className="text-button" onClick={() => openEdit(provider)}>
                    <Settings2 size={12} /> 编辑
                  </button>
                  {!provider.is_default && provider.kind !== "demo" && (
                    <button className="text-button danger" onClick={() => void removeProvider(provider)}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {editing && (
        <Modal
          open
          onClose={() => setEditing(null)}
          title={editing.id ? "编辑供应商" : "添加供应商"}
          eyebrow="PROVIDER / 配置"
          width={620}
          footer={
            <>
              <button className="button button-ghost" onClick={() => setEditing(null)}>
                取消
              </button>
              <button className="button button-primary" onClick={() => void saveDraft()} disabled={saving}>
                {saving ? <Loader2 size={15} className="spin" /> : <Check size={15} />}
                保存配置
              </button>
            </>
          }
        >
          <div className="provider-form">
            <div className="form-row two">
              <Field label="名称">
                <input className="input" value={editing.name} onChange={(event) => updateDraft({ name: event.target.value })} />
              </Field>
              <Field label="类型">
                <select
                  className="input"
                  value={editing.kind}
                  onChange={(event) => {
                    const next = newDraft(event.target.value as Provider["kind"]);
                    setEditing({ ...next, id: editing.id });
                  }}
                >
                  {(presets?.provider_kinds ?? []).map((kind) => (
                    <option key={kind.id} value={kind.id}>
                      {kind.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            {editing.kind !== "demo" && editing.kind !== "diffusers" && (
              <Field label="API 地址" hint="OpenAI 兼容端点请包含 /v1">
                <input
                  className="input"
                  value={editing.base_url}
                  onChange={(event) => updateDraft({ base_url: event.target.value })}
                  placeholder="https://api.openai.com/v1"
                />
              </Field>
            )}

            {(editing.kind === "openai" || editing.kind === "stability") && (
              <Field label="API Key" hint={editing.id ? "留空保持现有密钥" : "使用 Windows DPAPI 加密保存"}>
                <input
                  className="input"
                  type="password"
                  value={editing.api_key ?? ""}
                  onChange={(event) => updateDraft({ api_key: event.target.value, clear_secret: false })}
                  placeholder="sk-…"
                  autoComplete="off"
                />
              </Field>
            )}
            {editing.id && (editing.kind === "openai" || editing.kind === "stability") && (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(editing.clear_secret)}
                  onChange={(event) => updateDraft({ clear_secret: event.target.checked })}
                />
                清除已保存的密钥
              </label>
            )}

            <Field label="模型" hint={editing.kind === "diffusers" ? "Hugging Face ID 或本地文件夹" : "可手动填写模型 ID"}>
              <div className="input-with-action">
                <input
                  className="input"
                  value={editing.model}
                  list="provider-model-options"
                  onChange={(event) => updateDraft({ model: event.target.value })}
                />
                {(editing.kind === "comfyui" || editing.kind === "openai") && editing.id && (
                  <button className="button button-small button-ghost" onClick={() => void fetchModels()}>
                    {modelLoading ? <Spinner size={12} /> : <RefreshCw size={12} />}
                    获取
                  </button>
                )}
                <datalist id="provider-model-options">
                  {modelOptions.map((model) => (
                    <option value={model} key={model} />
                  ))}
                </datalist>
              </div>
            </Field>

            {editing.kind === "diffusers" && (
              <>
                <div className="form-row two">
                  <Field label="设备">
                    <select
                      className="input"
                      value={String(editing.options.device ?? "auto")}
                      onChange={(event) => updateDraft({ options: { ...editing.options, device: event.target.value } })}
                    >
                      <option value="auto">自动（优先 CUDA）</option>
                      <option value="cuda">CUDA</option>
                      <option value="cpu">CPU</option>
                    </select>
                  </Field>
                  <Field label="精度">
                    <select
                      className="input"
                      value={String(editing.options.dtype ?? "auto")}
                      onChange={(event) => updateDraft({ options: { ...editing.options, dtype: event.target.value } })}
                    >
                      <option value="auto">自动</option>
                      <option value="float16">FP16</option>
                      <option value="bfloat16">BF16</option>
                      <option value="float32">FP32</option>
                    </select>
                  </Field>
                </div>
                <div className="switch-row compact-row">
                  <div>
                    <strong>生成后释放模型</strong>
                    <span>适合与其他 AI 共用显卡</span>
                  </div>
                  <Toggle
                    checked={Boolean(editing.options.unload_after_generate ?? true)}
                    onChange={(value) => updateDraft({ options: { ...editing.options, unload_after_generate: value } })}
                    label="生成后释放模型"
                  />
                </div>
                <Field label="HF 镜像" hint="国内网络可填 https://hf-mirror.com">
                  <input
                    className="input"
                    value={String(editing.options.hf_endpoint ?? "")}
                    onChange={(event) => updateDraft({ options: { ...editing.options, hf_endpoint: event.target.value } })}
                    placeholder="https://hf-mirror.com"
                  />
                </Field>
              </>
            )}

            {editing.kind === "comfyui" && (
              <Field label="超时（秒）" hint="首次加载大模型可能需要更久">
                <input
                  className="input"
                  type="number"
                  min={30}
                  max={3600}
                  value={Number(editing.options.timeout ?? 420)}
                  onChange={(event) => updateDraft({ options: { ...editing.options, timeout: Number(event.target.value) } })}
                />
              </Field>
            )}

            <div className="switch-row compact-row">
              <div>
                <strong>启用此供应商</strong>
                <span>停用后不会出现在创作台的引擎列表</span>
              </div>
              <Toggle checked={editing.enabled} onChange={(value) => updateDraft({ enabled: value })} label="启用供应商" />
            </div>

            <details className="advanced-json">
              <summary>高级参数（JSON）</summary>
              <textarea
                className="input textarea-small mono"
                rows={4}
                value={editing.rawOptions}
                onChange={(event) => updateDraft({ rawOptions: event.target.value })}
              />
            </details>
          </div>
        </Modal>
      )}
    </div>
  );
}
