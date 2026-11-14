import {
  AlertTriangle,
  Download,
  FolderOpen,
  ExternalLink,
  HardDrive,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Field, Toggle } from "../components/Controls";
import { useStudio } from "../state/StudioContext";
import type { Settings } from "../types";

export function SettingsPage() {
  const { config, settings, providers, runtime, refreshSettings, notify, fail } = useStudio();
  const [form, setForm] = useState<Settings | null>(settings);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    if (settings && (!form || !dirty)) setForm(settings);
  }, [settings, form, dirty]);

  const update = (patch: Partial<Settings>) => {
    setForm((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  };

  const updateLocal = (patch: Partial<Settings["local_engine"]>) => {
    if (!form) return;
    update({ local_engine: { ...form.local_engine, ...patch } });
  };

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const next = await api.updateSettings(form);
      setForm(next);
      await refreshSettings();
      setDirty(false);
      notify("设置已保存");
    } catch (error) {
      fail(error, "保存设置失败");
    } finally {
      setSaving(false);
    }
  };

  const restart = async () => {
    if (!window.lumen) return;
    setRestarting(true);
    try {
      await window.lumen.restartBackend();
      window.location.reload();
    } catch (error) {
      fail(error, "重启本地服务失败");
      setRestarting(false);
    }
  };

  const pixelOptions = useMemo(
    () => [
      { value: 1_048_576, label: "1 MP · 1024² 级别" },
      { value: 2_097_152, label: "2 MP · 1448² 级别" },
      { value: 4_194_304, label: "4 MP · 2048² 级别" },
    ],
    [],
  );

  if (!form) {
    return (
      <div className="page">
        <div className="gallery-loading">
          <Loader2 className="spin" size={18} /> 正在读取设置…
        </div>
      </div>
    );
  }

  return (
    <div className="page settings-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">PREFERENCES / 设置</span>
          <h1>让工作流适合你</h1>
          <p>设置保存在本地 JSON 中，API 密钥由 Windows 数据保护接口加密。Lumen 不发遥测。</p>
        </div>
        <div className="header-actions">
          {dirty && <span className="dirty-badge">有未保存更改</span>}
          <button className="button button-primary" onClick={() => void save()} disabled={saving || !dirty}>
            {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
            保存设置
          </button>
        </div>
      </header>

      <div className="settings-layout">
        <div className="settings-main">
          <section className="settings-section">
            <div className="settings-head">
              <span className="settings-icon">
                <SlidersHorizontal size={17} />
              </span>
              <div>
                <h2>创作默认值</h2>
                <p>新建作品时自动带入，可在创作台临时覆盖。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <Field label="默认引擎">
                <select
                  className="input"
                  value={form.default_provider_id}
                  onChange={(event) => update({ default_provider_id: event.target.value })}
                >
                  {providers.filter((provider) => provider.enabled).map((provider) => (
                    <option value={provider.id} key={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="默认画幅">
                <select className="input" value={form.default_aspect} onChange={(event) => update({ default_aspect: event.target.value })}>
                  <option value="1:1">1:1 方形</option>
                  <option value="4:3">4:3 经典</option>
                  <option value="3:4">3:4 竖版</option>
                  <option value="3:2">3:2 相机</option>
                  <option value="16:9">16:9 宽屏</option>
                  <option value="9:16">9:16 竖屏</option>
                  <option value="21:9">21:9 超宽</option>
                </select>
              </Field>
              <Field label="默认长边" hint="512–2048">
                <input
                  className="input"
                  type="number"
                  min={512}
                  max={2048}
                  step={64}
                  value={form.default_long_edge}
                  onChange={(event) => update({ default_long_edge: Number(event.target.value) })}
                />
              </Field>
              <Field label="默认采样器">
                <select className="input" value={form.default_scheduler} onChange={(event) => update({ default_scheduler: event.target.value })}>
                  <option value="auto">自动</option>
                  <option value="dpmpp_2m_karras">DPM++ 2M Karras</option>
                  <option value="euler">Euler</option>
                  <option value="euler_a">Euler a</option>
                  <option value="lcm">LCM</option>
                  <option value="ddim">DDIM</option>
                </select>
              </Field>
            </div>
            <div className="settings-switches">
              <div className="switch-row">
                <div>
                  <strong>默认开启自动调参</strong>
                  <span>让本地偏好模型参与步数与 CFG 选择</span>
                </div>
                <Toggle checked={form.auto_tune_default} onChange={(value) => update({ auto_tune_default: value })} label="默认自动调参" />
              </div>
              <div className="switch-row">
                <div>
                  <strong>自动分析图像</strong>
                  <span>生成后计算清晰度、曝光、色彩与构图</span>
                </div>
                <Toggle checked={form.auto_analyze} onChange={(value) => update({ auto_analyze: value })} label="自动分析图像" />
              </div>
            </div>
          </section>

          <section className="settings-section">
            <div className="settings-head">
              <span className="settings-icon">
                <HardDrive size={17} />
              </span>
              <div>
                <h2>生成与存储</h2>
                <p>限制单张像素与批量数量，避免显存或磁盘压力。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <Field label="单张像素上限">
                <select
                  className="input"
                  value={form.max_pixels}
                  onChange={(event) => update({ max_pixels: Number(event.target.value) })}
                >
                  {pixelOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="单次批量上限">
                <select className="input" value={form.max_batch} onChange={(event) => update({ max_batch: Number(event.target.value) })}>
                  {[1, 2, 3, 4].map((value) => (
                    <option value={value} key={value}>
                      {value} 张
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="path-box">
              <FolderOpen size={15} />
              <div>
                <span>数据目录</span>
                <strong>{runtime?.data_dir ?? "—"}</strong>
              </div>
              <button className="text-button" onClick={() => runtime?.data_dir && void window.lumen?.openPath(runtime.data_dir)}>
                打开
              </button>
            </div>
            <div className="inline-actions">
              <a className="button button-ghost button-small" href={api.mediaUrl("/api/export/library")} download>
                <Download size={13} /> 导出作品元数据
              </a>
              <button
                className="button button-ghost button-small"
                onClick={() => {
                  const log = runtime?.data_dir ? `${runtime.data_dir}\\logs` : "";
                  if (log) void window.lumen?.openPath(log);
                }}
              >
                <FolderOpen size={13} /> 打开日志目录
              </button>
            </div>
          </section>

          <section className="settings-section">
            <div className="settings-head">
              <span className="settings-icon">
                <ShieldCheck size={17} />
              </span>
              <div>
                <h2>隐私与本地数据</h2>
                <p>本地推理不会上传图片。只有你主动选择云端供应商时，提示词与参考图才会发送给对应服务。</p>
              </div>
            </div>
            <div className="settings-switches">
              <div className="switch-row">
                <div>
                  <strong>从 PNG 中移除生成参数</strong>
                  <span>分享原图时避免泄露提示词；应用内仍保留元数据</span>
                </div>
                <Toggle
                  checked={form.privacy.strip_png_metadata}
                  onChange={(value) => update({ privacy: { ...form.privacy, strip_png_metadata: value } })}
                  label="移除 PNG 元数据"
                />
              </div>
              <div className="switch-row">
                <div>
                  <strong>保留参考图上传缓存</strong>
                  <span>关闭后生成完成即删除参考图临时文件</span>
                </div>
                <Toggle
                  checked={form.privacy.keep_init_uploads}
                  onChange={(value) => update({ privacy: { ...form.privacy, keep_init_uploads: value } })}
                  label="保留参考图缓存"
                />
              </div>
            </div>
            <div className="security-note">
              <Lock size={15} />
              <p>
                API Key 使用 Windows DPAPI 按当前用户加密，保存在本地。前端只能看到掩码，导出设置不包含密钥。
              </p>
            </div>
          </section>

          <section className="settings-section">
            <div className="settings-head">
              <span className="settings-icon">
                <RefreshCw size={17} />
              </span>
              <div>
                <h2>本地引擎</h2>
                <p>修改后部分设置需要重启本地服务生效。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <Field label="默认本地模型">
                <input
                  className="input"
                  value={form.local_engine.model}
                  onChange={(event) => updateLocal({ model: event.target.value })}
                  placeholder="stabilityai/sd-turbo"
                />
              </Field>
              <Field label="HF 镜像地址" hint="国内网络可选">
                <input
                  className="input"
                  value={form.local_engine.hf_endpoint}
                  onChange={(event) => updateLocal({ hf_endpoint: event.target.value })}
                  placeholder="https://hf-mirror.com"
                />
              </Field>
            </div>
            <div className="settings-switches">
              <div className="switch-row">
                <div>
                  <strong>低显存守护</strong>
                  <span>顺序卸载、VAE 分块、生成后释放；与其他 AI 共用显卡时推荐</span>
                </div>
                <Toggle
                  checked={Boolean(form.local_engine.low_vram)}
                  onChange={(value) => updateLocal({ low_vram: value, unload_after_generate: value })}
                  label="低显存守护"
                />
              </div>
              <div className="switch-row">
                <div>
                  <strong>仅使用本地模型缓存</strong>
                  <span>禁止在线下载；适合完全离线环境</span>
                </div>
                <Toggle
                  checked={form.local_engine.local_files_only}
                  onChange={(value) => updateLocal({ local_files_only: value })}
                  label="仅使用本地缓存"
                />
              </div>
            </div>
            <div className="inline-actions">
              <button className="button button-ghost button-small" onClick={() => void restart()} disabled={restarting}>
                {restarting ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                重启本地服务
              </button>
            </div>
          </section>
        </div>

        <aside className="settings-aside">
          <section className="about-card">
            <span className="about-mark">L</span>
            <span className="eyebrow">LUMEN STUDIO</span>
            <h2>本地优先的 AI 画室</h2>
            <p>v{config.version} · MIT License</p>
            <div className="about-rows">
              <div>
                <span>本地引擎</span>
                <strong>{runtime?.local_engine.available ? "已就绪" : "未安装"}</strong>
              </div>
              <div>
                <span>GPU</span>
                <strong>{runtime?.system.gpus[0]?.name ?? "CPU"}</strong>
              </div>
              <div>
                <span>可用显存</span>
                <strong>{runtime?.free_vram_mb ? `${(runtime.free_vram_mb / 1024).toFixed(1)} GB` : "—"}</strong>
              </div>
              <div>
                <span>磁盘剩余</span>
                <strong>{runtime?.disk_free_gb ? `${runtime.disk_free_gb} GB` : "—"}</strong>
              </div>
            </div>
            <a className="button button-ghost button-small" href="https://github.com/7ather-LX/lumen-studio" target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> 项目主页
            </a>
          </section>

          <section className="hint-card">
            <h3>
              <Info size={15} /> 推荐配置
            </h3>
            <ul>
              <li>
                <strong>最低：</strong>4 核 CPU / 16 GB 内存，CPU 推理可出图但较慢
              </li>
              <li>
                <strong>推荐：</strong>RTX 3060 12 GB / 4070 12 GB，32 GB 内存
              </li>
              <li>
                <strong>共用显卡：</strong>剩余 2–6 GB 时开启低显存守护，使用 SD-Turbo 512
              </li>
              <li>
                <strong>舒适：</strong>16 GB+ 显存可运行 SDXL / FLUX 高分辨率
              </li>
            </ul>
            <p>NPU 支持通过 ComfyUI 的 OpenVINO / DirectML 后端实现，属于实验性路径。</p>
          </section>

          <section className="hint-card warn-card">
            <h3>
              <AlertTriangle size={15} /> 注意
            </h3>
            <p>云端供应商可能按张计费，并受其内容政策约束。使用前请在对应平台确认价格与条款。</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
