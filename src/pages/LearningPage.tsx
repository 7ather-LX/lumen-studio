import {
  ArrowRight,
  Brain,
  Check,
  ChevronRight,
  Cpu,
  Gauge,
  RefreshCw,
  Sparkles,
  Star,
  TrendingUp,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Spinner, Toggle } from "../components/Controls";
import { cn, formatDate } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { Insights, PageId } from "../types";

export function LearningPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const { presets, galleryVersion, settings, refreshSettings, notify, fail } = useStudio();
  const [insights, setInsights] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);

  const load = useCallback(async () => {
    try {
      setInsights(await api.insights());
    } catch (error) {
      fail(error, "无法读取学习数据");
    } finally {
      setLoading(false);
    }
  }, [fail]);

  useEffect(() => {
    void load();
  }, [load, galleryVersion]);

  const toggleAdaptive = async (key: "adaptive_enabled" | "adaptive_prompt", value: boolean) => {
    try {
      const nextSettings = await api.updateSettings({ [key]: value });
      await refreshSettings();
      setInsights((current) => (current ? { ...current, [key]: value } : current));
      notify(key === "adaptive_enabled" ? (value ? "已开启自动调参" : "已暂停自动调参") : value ? "已开启提示词学习" : "已暂停提示词学习", `当前设置：${nextSettings[key] ? "开启" : "关闭"}`);
    } catch (error) {
      fail(error, "更新学习设置失败");
    }
  };

  const train = async () => {
    setTraining(true);
    try {
      const result = await api.trainLearning();
      setInsights(result.insights);
      notify(result.ok ? "偏好模型已重新训练" : "样本还不够，先给几张作品评分");
    } catch (error) {
      fail(error, "训练失败");
    } finally {
      setTraining(false);
    }
  };

  const styleLabel = useMemo(() => {
    const map = new Map((presets?.styles ?? []).map((style) => [style.id, style.label]));
    return (id: string) => map.get(id) ?? id;
  }, [presets?.styles]);

  if (loading) {
    return (
      <div className="page learning-page">
        <div className="gallery-loading">
          <Spinner size={20} /> 正在读取本地学习模型…
        </div>
      </div>
    );
  }

  const stage = insights?.stage ?? "探索期";
  const accuracy = insights?.model?.cross_val_accuracy ?? insights?.model?.train_accuracy ?? null;
  const quality = insights?.quality;
  const totalFeedback = insights?.feedback_samples ?? 0;

  return (
    <div className="page learning-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">LEARNING / 学习中心</span>
          <h1>越画，越像你</h1>
          <p>每次评分都会留在本机。Lumen 用这些偏好调整参数、采样器和提示词，不训练、也不上传任何图片。</p>
        </div>
        <div className="header-actions">
          <div className={cn("stage-pill", stage === "已适应" ? "done" : stage === "学习中" ? "active" : "")}>
            <span className="pulse-dot" />
            {stage}
          </div>
          <button className="button button-ghost" onClick={() => void train()} disabled={training}>
            {training ? <Spinner size={14} /> : <RefreshCw size={14} />}
            重新训练
          </button>
        </div>
      </header>

      <div className="learning-summary">
        <div className="learning-copy">
          <span className="eyebrow">LOCAL PREFERENCE MODEL</span>
          <h2>{insights?.summary}</h2>
          <div className="learning-switches">
            <div className="switch-row compact-row">
              <div>
                <strong>自动参数调优</strong>
                <span>用历史评分选择步数、CFG 与采样器</span>
              </div>
              <Toggle
                checked={Boolean(settings?.adaptive_enabled ?? insights?.adaptive_enabled)}
                onChange={(value) => void toggleAdaptive("adaptive_enabled", value)}
                label="自动参数调优"
              />
            </div>
            <div className="switch-row compact-row">
              <div>
                <strong>提示词偏好</strong>
                <span>把高评价作品中的关键词融入后续提示</span>
              </div>
              <Toggle
                checked={Boolean(settings?.adaptive_prompt ?? insights?.adaptive_prompt)}
                onChange={(value) => void toggleAdaptive("adaptive_prompt", value)}
                label="提示词偏好"
              />
            </div>
          </div>
        </div>
        <div className="learning-orb">
          <div className="orb-ring" />
          <Brain size={36} />
          <span>{totalFeedback}</span>
          <small>FEEDBACK</small>
        </div>
      </div>

      <div className="stat-row learning-stats">
        <div className="mini-stat">
          <span>有效反馈</span>
          <strong>{totalFeedback}</strong>
        </div>
        <div className="mini-stat">
          <span>平均技术质量</span>
          <strong>{quality?.average ?? "—"}</strong>
        </div>
        <div className="mini-stat">
          <span>近期质量变化</span>
          <strong className={(quality?.recent_delta ?? 0) >= 0 ? "positive" : "negative"}>
            {quality?.recent_delta === null || quality?.recent_delta === undefined
              ? "—"
              : `${quality.recent_delta > 0 ? "+" : ""}${quality.recent_delta}`}
          </strong>
        </div>
        <div className="mini-stat">
          <span>模型准确率</span>
          <strong>{accuracy !== null ? `${Math.round(accuracy * 100)}%` : "—"}</strong>
        </div>
      </div>

      <div className="learning-grid">
        <section className="panel chart-panel">
          <div className="panel-head">
            <div>
              <span className="section-title">质量趋势</span>
              <span className="section-meta">最近 30 张作品的技术分析</span>
            </div>
            <span className="chart-legend">
              <span /> 技术质量
            </span>
          </div>
          <QualityChart trend={quality?.trend ?? []} />
          <p className="panel-foot">
            技术质量由清晰度、曝光、对比、色彩、构图综合计算；它不代表你的审美，你的星级才是偏好信号。
          </p>
        </section>

        <section className="panel model-panel">
          <div className="panel-head">
            <div>
              <span className="section-title">偏好模型</span>
              <span className="section-meta">LOGISTIC RANKER</span>
            </div>
            <span className={cn("model-state", insights?.model ? "ready" : "")}>
              {insights?.model ? "已训练" : "等待样本"}
            </span>
          </div>
          <div className="model-metrics">
            <div>
              <span>样本</span>
              <strong>{insights?.model?.samples ?? 0}</strong>
            </div>
            <div>
              <span>特征维度</span>
              <strong>{insights?.model?.weights ?? 0}</strong>
            </div>
            <div>
              <span>训练集准确率</span>
              <strong>{insights?.model?.train_accuracy !== null && insights?.model?.train_accuracy !== undefined ? `${Math.round(insights.model.train_accuracy * 100)}%` : "—"}</strong>
            </div>
            <div>
              <span>交叉验证</span>
              <strong>{accuracy !== null ? `${Math.round(accuracy * 100)}%` : "—"}</strong>
            </div>
          </div>
          <div className="model-timestamp">
            {insights?.model?.trained_at ? `最近训练：${formatDate(insights.model.trained_at)}` : "给作品评分，模型会自动开始学习"}
          </div>
          {insights?.suggestion && (
            <div className="suggestion-card">
              <div className="suggestion-head">
                <Sparkles size={14} />
                <span>当前推荐参数</span>
                <strong>{Math.round(insights.suggestion.confidence * 100)}% 置信</strong>
              </div>
              <div className="suggestion-values">
                <span>{insights.suggestion.steps} 步</span>
                <span>CFG {insights.suggestion.guidance}</span>
                <span>{insights.suggestion.scheduler}</span>
              </div>
              <p>{insights.suggestion.reason}</p>
            </div>
          )}
          {!insights?.model && (
            <button className="button button-ghost model-empty-action" onClick={() => onNavigate("gallery")}>
              <Star size={14} /> 去给作品评分 <ArrowRight size={13} />
            </button>
          )}
        </section>
      </div>

      <div className="learning-grid wide">
        <section className="panel">
          <div className="panel-head">
            <div>
              <span className="section-title">提示词偏好</span>
              <span className="section-meta">从高分与低分作品的差异中提取</span>
            </div>
            <Wand2 size={16} className="panel-icon" />
          </div>
          {totalFeedback < 4 ? (
            <div className="panel-empty">
              <p>至少需要 4 条评分才能提取可靠的提示词差异。</p>
              <button className="text-button" onClick={() => onNavigate("create")}>
                去创作 <ChevronRight size={13} />
              </button>
            </div>
          ) : (
            <div className="token-columns">
              <div>
                <span className="token-title positive">
                  <TrendingUp size={13} /> 正相关
                </span>
                <div className="token-cloud">
                  {insights?.tokens.positive.length ? (
                    insights.tokens.positive.map((token) => (
                      <span className="token positive" key={token.token}>
                        {token.token}
                        <small>+{token.lift.toFixed(2)}</small>
                      </span>
                    ))
                  ) : (
                    <span className="muted">暂未发现明显正相关词</span>
                  )}
                </div>
              </div>
              <div>
                <span className="token-title negative">
                  <Gauge size={13} /> 负相关
                </span>
                <div className="token-cloud">
                  {insights?.tokens.negative.length ? (
                    insights.tokens.negative.map((token) => (
                      <span className="token negative" key={token.token}>
                        {token.token}
                        <small>{token.lift.toFixed(2)}</small>
                      </span>
                    ))
                  ) : (
                    <span className="muted">暂未发现明显负相关词</span>
                  )}
                </div>
              </div>
            </div>
          )}
          <p className="panel-foot">
            这些词只会作为建议融入提示词，不会覆盖你写的主体描述。可在上方随时关闭。
          </p>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <span className="section-title">风格与引擎</span>
              <span className="section-meta">按你的平均评分排序</span>
            </div>
            <Cpu size={16} className="panel-icon" />
          </div>
          <div className="rank-list">
            {(insights?.styles ?? []).slice(0, 5).map((style) => (
              <div className="rank-row" key={style.style}>
                <span className="rank-label">{styleLabel(style.style)}</span>
                <div className="rank-track">
                  <span
                    className={style.avg_reward >= 0 ? "positive" : "negative"}
                    style={{ width: `${Math.max(8, Math.min(100, ((style.avg_reward + 1) / 2) * 100))}%` }}
                  />
                </div>
                <strong>{style.avg_reward.toFixed(2)}</strong>
                <small>{style.count} 次</small>
              </div>
            ))}
            {!insights?.styles.length && <p className="muted">还没有足够的评分数据。</p>}
          </div>
          <div className="provider-rank">
            {(insights?.providers ?? []).map((provider) => (
              <span key={provider.provider_id}>
                <Check size={12} /> {provider.provider_id} · {provider.avg_reward.toFixed(2)}
              </span>
            ))}
          </div>
        </section>
      </div>

      <section className="how-it-learns">
        <div className="how-head">
          <span className="eyebrow">HOW IT LEARNS</span>
          <h2>透明、可关闭的学习闭环</h2>
        </div>
        <div className="how-steps">
          <div>
            <span>01</span>
            <strong>生成</strong>
            <p>记录提示词、尺寸、步数、CFG、采样器与种子。</p>
          </div>
          <div>
            <span>02</span>
            <strong>分析</strong>
            <p>本地计算清晰度、曝光、色彩、构图与相似度。</p>
          </div>
          <div>
            <span>03</span>
            <strong>反馈</strong>
            <p>你的星级与收藏成为偏好模型的训练信号。</p>
          </div>
          <div>
            <span>04</span>
            <strong>迭代</strong>
            <p>推荐参数与提示词片段，在下一张图生效。</p>
          </div>
        </div>
        <p className="how-note">
          当前版本不自动微调模型权重，也不会把图片发送到任何服务器。若未来加入 LoRA 训练，会作为独立、明确授权的功能。
        </p>
      </section>
    </div>
  );
}

function QualityChart({ trend }: { trend: Insights["quality"]["trend"] }) {
  const points = trend.slice(-30);
  if (points.length < 2) {
    return (
      <div className="chart-empty">
        <Gauge size={22} />
        <p>生成至少两张作品后，这里会出现质量趋势。</p>
      </div>
    );
  }
  const width = 620;
  const height = 180;
  const padding = 12;
  const coords = points.map((point, index) => ({
    x: padding + (index / (points.length - 1)) * (width - padding * 2),
    y: padding + (1 - point.quality / 100) * (height - padding * 2),
  }));
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].x},${height - padding} L${coords[0].x},${height - padding} Z`;
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="技术质量趋势">
        <defs>
          <linearGradient id="quality-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#c9f56d" stopOpacity="0.28" />
            <stop offset="1" stopColor="#c9f56d" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[25, 50, 75].map((value) => (
          <line
            key={value}
            x1={padding}
            x2={width - padding}
            y1={padding + (1 - value / 100) * (height - padding * 2)}
            y2={padding + (1 - value / 100) * (height - padding * 2)}
            className="chart-grid-line"
          />
        ))}
        <path d={area} fill="url(#quality-area)" />
        <path d={line} className="chart-line" />
        {coords.map((point, index) => (
          <circle key={points[index].id} cx={point.x} cy={point.y} r={points.length > 18 ? 2 : 3} className="chart-dot" />
        ))}
      </svg>
      <div className="chart-axis">
        <span>{formatDate(points[0].date)}</span>
        <span>{formatDate(points[points.length - 1].date)}</span>
      </div>
    </div>
  );
}
