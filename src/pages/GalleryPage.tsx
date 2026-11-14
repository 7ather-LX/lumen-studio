import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  FolderOpen,
  Heart,
  ImagePlus,
  Images,
  Layers,
  Loader2,
  Scissors,
  Search,
  Sparkles,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { CropDialog } from "../components/CropDialog";
import { Modal } from "../components/Modal";
import { Spinner, StarRating } from "../components/Controls";
import { cn, formatDate, formatMs, ratioLabel, truncate } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { PageId, StudioImage } from "../types";

type Filter = "all" | "favorites" | "rated" | "txt2img" | "img2img";
type Sort = "newest" | "oldest" | "rating";

function modeLabel(mode: StudioImage["mode"]): string {
  if (mode === "img2img") return "图生图";
  if (mode === "crop") return "裁切";
  return "文生图";
}

export function GalleryPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const { stats, galleryVersion, notify, fail, bumpGallery } = useStudio();
  const [items, setItems] = useState<StudioImage[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<StudioImage | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 320);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const load = useCallback(
    async (offset = 0, append = false) => {
      const id = ++requestId.current;
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const result = await api.images({
          limit: 48,
          offset,
          favorite: filter === "favorites" ? true : undefined,
          mode: filter === "txt2img" || filter === "img2img" ? filter : undefined,
          min_rating: filter === "rated" ? 3 : undefined,
          search: search || undefined,
          sort,
        });
        if (id !== requestId.current) return;
        setItems((current) => (append ? [...current, ...result.items] : result.items));
        setTotal(result.total);
      } catch (error) {
        if (id === requestId.current) fail(error, "无法加载作品库");
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [filter, search, sort, fail],
  );

  useEffect(() => {
    void load(0, false);
  }, [load, galleryVersion]);

  const updateImage = useCallback((image: StudioImage) => {
    setItems((current) => current.map((item) => (item.id === image.id ? image : item)));
    setSelected((current) => (current?.id === image.id ? image : current));
  }, []);

  const toggleFavorite = async (image: StudioImage) => {
    try {
      const result = await api.feedback(image.id, { favorite: !image.favorite });
      updateImage(result.image);
      bumpGallery();
    } catch (error) {
      fail(error, "更新收藏失败");
    }
  };

  const reuse = (image: StudioImage) => {
    onNavigate("create");
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("lumen:reuse", { detail: image }));
    }, 80);
  };

  const useReference = (image: StudioImage) => {
    onNavigate("create");
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("lumen:reuse", { detail: { ...image, mode: "img2img" } }));
    }, 80);
  };

  const created = (image: StudioImage) => {
    setItems((current) => [image, ...current]);
    setTotal((value) => value + 1);
    setSelected(image);
    bumpGallery();
  };

  const remove = async (image: StudioImage) => {
    if (!window.confirm("删除这张作品？原图与缩略图会从本地磁盘移除。")) return;
    try {
      await api.deleteImage(image.id);
      setItems((current) => current.filter((item) => item.id !== image.id));
      setSelected(null);
      setTotal((value) => Math.max(0, value - 1));
      bumpGallery();
      notify("作品已删除");
    } catch (error) {
      fail(error, "删除失败");
    }
  };

  const filters: Array<{ id: Filter; label: string }> = [
    { id: "all", label: "全部" },
    { id: "favorites", label: "收藏" },
    { id: "rated", label: "高分" },
    { id: "txt2img", label: "文生图" },
    { id: "img2img", label: "图生图" },
  ];

  return (
    <div className="page gallery-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">LIBRARY / 作品库</span>
          <h1>你的图像档案</h1>
          <p>所有图片、参数与评分都保存在本地。给作品打分，Lumen 会慢慢学会你的审美。</p>
        </div>
        <div className="header-actions">
          <a className="button button-ghost" href={api.mediaUrl("/api/export/library")} download>
            <Download size={15} />
            导出元数据
          </a>
          <button className="button button-primary" onClick={() => onNavigate("create")}>
            <Sparkles size={15} />
            新建作品
          </button>
        </div>
      </header>

      <div className="stat-row">
        <div className="mini-stat">
          <span>作品总数</span>
          <strong>{stats?.images ?? 0}</strong>
        </div>
        <div className="mini-stat">
          <span>收藏</span>
          <strong>{stats?.favorites ?? 0}</strong>
        </div>
        <div className="mini-stat">
          <span>已评分</span>
          <strong>{stats?.rated ?? 0}</strong>
        </div>
        <div className="mini-stat">
          <span>本地占用</span>
          <strong>{(stats?.storage_mb ?? 0).toFixed(0)} MB</strong>
        </div>
      </div>

      <div className="gallery-toolbar">
        <div className="filter-group">
          {filters.map((item) => (
            <button
              key={item.id}
              className={cn("filter-chip", filter === item.id && "active")}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <label className="search-field">
            <Search size={14} />
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="搜索提示词、标签…"
            />
            {searchInput && (
              <button className="icon-button tiny" onClick={() => setSearchInput("")} aria-label="清除搜索">
                <X size={12} />
              </button>
            )}
          </label>
          <select className="input compact" value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
            <option value="newest">最新</option>
            <option value="oldest">最早</option>
            <option value="rating">评分</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="gallery-loading">
          <Spinner size={20} />
          <span>正在整理作品…</span>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <Images size={28} />
          </div>
          <h2>{search ? "没有匹配的作品" : "还没有作品"}</h2>
          <p>{search ? "换一个关键词试试，或清空筛选。" : "从一句描述开始，创作第一张属于你的画面。"}</p>
          <button className="button button-primary" onClick={() => onNavigate("create")}>
            <Sparkles size={15} /> 去创作
          </button>
        </div>
      ) : (
        <>
          <div className="gallery-masonry">
            {items.map((image) => (
              <article className="image-card" key={image.id}>
                <button className="image-open" onClick={() => setSelected(image)}>
                  <div className="card-image" style={{ aspectRatio: `${image.width} / ${image.height}` }}>
                    <img src={api.imageUrl(image, true)} alt={image.prompt} loading="lazy" />
                    <div className="card-shade" />
                    <span className="card-mode">{modeLabel(image.mode)}</span>
                    <span className="card-open-hint">查看</span>
                  </div>
                  <div className="card-copy">
                    <p>{truncate(image.prompt, 88)}</p>
                    <div className="card-meta">
                      <span>
                        {image.width} × {image.height}
                      </span>
                      <span>{ratioLabel(image.width, image.height)}</span>
                      {image.rating ? (
                        <span className="card-rating">
                          <Star size={11} fill="currentColor" /> {image.rating}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </button>
                <button
                  className={cn("card-heart", image.favorite && "active")}
                  onClick={() => void toggleFavorite(image)}
                  aria-label={image.favorite ? "取消收藏" : "收藏"}
                >
                  <Heart size={15} fill={image.favorite ? "currentColor" : "none"} />
                </button>
              </article>
            ))}
          </div>
          {items.length < total && (
            <div className="load-more">
              <button className="button button-ghost" onClick={() => void load(items.length, true)} disabled={loadingMore}>
                {loadingMore ? <Loader2 size={15} className="spin" /> : <Layers size={15} />}
                加载更多
              </button>
              <span>
                {items.length} / {total}
              </span>
            </div>
          )}
        </>
      )}

      {selected && (
        <ImageDetail
          key={selected.id}
          image={selected}
          onClose={() => setSelected(null)}
          onChange={updateImage}
          onCreated={created}
          onReuse={reuse}
          onReference={useReference}
          onDelete={remove}
          onFavorite={toggleFavorite}
        />
      )}
    </div>
  );
}

function ImageDetail({
  image,
  onClose,
  onChange,
  onCreated,
  onReuse,
  onReference,
  onDelete,
  onFavorite,
}: {
  image: StudioImage;
  onClose: () => void;
  onChange: (image: StudioImage) => void;
  onCreated: (image: StudioImage) => void;
  onReuse: (image: StudioImage) => void;
  onReference: (image: StudioImage) => void;
  onDelete: (image: StudioImage) => void;
  onFavorite: (image: StudioImage) => void;
}) {
  const { notify, fail, bumpGallery } = useStudio();
  const [notes, setNotes] = useState(image.notes);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [cropping, setCropping] = useState(false);
  const analysis = image.analysis ?? {};
  const palette = analysis.palette ?? [];
  const metrics = useMemo(
    () =>
      [
        ["清晰度", analysis.sharpness],
        ["曝光", analysis.exposure],
        ["对比度", analysis.contrast],
        ["色彩", analysis.colorfulness],
        ["构图", analysis.composition],
        ["技术质量", analysis.technical_score],
      ].filter((entry): entry is [string, number] => typeof entry[1] === "number"),
    [analysis],
  );

  const rate = async (value: number) => {
    try {
      const result = await api.feedback(image.id, { rating: value });
      onChange(result.image);
      bumpGallery();
      notify(`已记录 ${value} 星反馈`);
    } catch (error) {
      fail(error, "记录评分失败");
    }
  };

  const saveNotes = async () => {
    setSaving(true);
    try {
      const next = await api.patchImage(image.id, { notes });
      onChange(next);
      notify("笔记已保存");
    } catch (error) {
      fail(error, "保存笔记失败");
    } finally {
      setSaving(false);
    }
  };

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(image.prompt);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      fail(new Error("剪贴板不可用"), "复制失败");
    }
  };

  const reveal = async () => {
    try {
      const result = await api.revealImage(image.id);
      if (window.lumen) await window.lumen.showInFolder(result.path);
      else notify("图片路径", result.path);
    } catch (error) {
      fail(error, "无法定位文件");
    }
  };

  return (
    <>
      <Modal open onClose={onClose} title="作品详情" eyebrow="IMAGE / 本地档案" width={1120}>
        <div className="image-detail">
        <div className="detail-canvas">
          <img src={api.imageUrl(image)} alt={image.prompt} />
          <div className="detail-canvas-actions">
            <button className={cn("icon-button", image.favorite && "liked")} onClick={() => onFavorite(image)}>
              <Heart size={17} fill={image.favorite ? "currentColor" : "none"} />
            </button>
            <a className="icon-button" href={api.mediaUrl(image.file_url, { download: true })} download>
              <Download size={17} />
            </a>
          </div>
        </div>
        <div className="detail-side">
          <div className="detail-side-head">
            <span className={cn("mode-badge", image.mode)}>{modeLabel(image.mode)}</span>
            <span className="detail-date">{formatDate(image.created_at)}</span>
          </div>
          <div className="detail-prompt-block">
            <div className="detail-prompt-head">
              <span>提示词</span>
              <button className="text-button" onClick={() => void copyPrompt()}>
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? "已复制" : "复制"}
              </button>
            </div>
            <p>{image.prompt}</p>
            {image.negative_prompt ? (
              <p className="negative-prompt">
                <strong>负面：</strong>
                {image.negative_prompt}
              </p>
            ) : null}
          </div>

          <div className="detail-stats">
            <div>
              <span>尺寸</span>
              <strong>
                {image.width} × {image.height}
              </strong>
            </div>
            <div>
              <span>步数</span>
              <strong>{image.steps}</strong>
            </div>
            <div>
              <span>CFG</span>
              <strong>{image.guidance}</strong>
            </div>
            <div>
              <span>种子</span>
              <strong className="mono">{image.seed}</strong>
            </div>
            <div>
              <span>耗时</span>
              <strong>{formatMs(image.generation_ms)}</strong>
            </div>
            <div>
              <span>引擎</span>
              <strong>{image.provider_name}</strong>
            </div>
          </div>

          <div className="analysis-block">
            <div className="analysis-head">
              <span>图像分析</span>
              <strong>{analysis.technical_score ?? "—"}<small>/100</small></strong>
            </div>
            <div className="metric-list">
              {metrics.map(([label, value]) => (
                <div className="metric-row" key={label}>
                  <span>{label}</span>
                  <div className="metric-bar">
                    <span style={{ width: `${Math.min(100, value)}%` }} />
                  </div>
                  <strong>{Math.round(value)}</strong>
                </div>
              ))}
            </div>
            {analysis.tags?.length ? (
              <div className="tag-row">
                {analysis.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            ) : null}
            {palette.length > 0 && (
              <div className="palette-row">
                {palette.map((color, index) => (
                  <span key={`${color.hex}-${index}`} style={{ background: color.hex }} title={color.hex} />
                ))}
              </div>
            )}
          </div>

          <div className="detail-rating-row">
            <span>你的评价</span>
            <StarRating value={image.rating} onChange={(value) => void rate(value)} />
          </div>

          <div className="notes-block">
            <textarea
              className="input textarea-small"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="记录这张图的灵感、问题或下一步尝试…"
              rows={3}
            />
            <button className="button button-small button-ghost" onClick={() => void saveNotes()} disabled={saving}>
              {saving ? <Spinner size={13} /> : <Check size={13} />}
              保存笔记
            </button>
          </div>

          <div className="detail-actions-row">
            {image.mode !== "crop" && (
              <button className="button button-ghost" onClick={() => onReuse(image)}>
                <Sparkles size={14} /> 复用参数
              </button>
            )}
            <button className="button button-ghost" onClick={() => setCropping(true)}>
              <Scissors size={14} /> 裁切
            </button>
            <button className="button button-ghost" onClick={() => onReference(image)}>
              <ImagePlus size={14} /> 继续生成
            </button>
            <button className="button button-ghost" onClick={() => void reveal()}>
              <FolderOpen size={14} /> 文件位置
            </button>
            <button className="button button-danger-ghost" onClick={() => onDelete(image)}>
              <Trash2 size={14} /> 删除
            </button>
          </div>
          <p className="detail-foot">
            <ArrowLeft size={12} /> 复用参数会回到创作台；继续生成会以这张图作为图生图参考
          </p>
        </div>
      </div>
    </Modal>
      {cropping && (
        <CropDialog image={image} onClose={() => setCropping(false)} onCropped={onCreated} />
      )}
    </>
  );
}
