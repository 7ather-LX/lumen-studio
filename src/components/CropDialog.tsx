import { Crop, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { api } from "../api";
import { cn } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { StudioImage } from "../types";
import { Modal } from "./Modal";

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

type DragMode = "move" | "nw" | "ne" | "sw" | "se";

const RATIOS: Array<{ id: string; label: string; value: number | null }> = [
  { id: "free", label: "自由", value: null },
  { id: "1:1", label: "1:1", value: 1 },
  { id: "4:3", label: "4:3", value: 4 / 3 },
  { id: "3:4", label: "3:4", value: 3 / 4 },
  { id: "16:9", label: "16:9", value: 16 / 9 },
  { id: "9:16", label: "9:16", value: 9 / 16 },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function CropDialog({
  image,
  onClose,
  onCropped,
}: {
  image: StudioImage;
  onClose: () => void;
  onCropped: (image: StudioImage) => void;
}) {
  const { notify, fail } = useStudio();
  const [box, setBox] = useState<Box>({ x: 0.08, y: 0.08, width: 0.84, height: 0.84 });
  const [ratio, setRatio] = useState("free");
  const [drag, setDrag] = useState<{ mode: DragMode; startX: number; startY: number; box: Box } | null>(null);
  const [busy, setBusy] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  const display = useMemo(() => {
    const maxW = 660;
    const maxH = 500;
    const scale = Math.min(maxW / image.width, maxH / image.height, 1);
    return {
      width: Math.max(240, Math.round(image.width * scale)),
      height: Math.max(160, Math.round(image.height * scale)),
    };
  }, [image.width, image.height]);

  const pixelWidth = Math.max(1, Math.round(box.width * image.width));
  const pixelHeight = Math.max(1, Math.round(box.height * image.height));

  useEffect(() => {
    if (!drag) return;
    const move = (event: PointerEvent) => {
      event.preventDefault();
      const dx = (event.clientX - drag.startX) / display.width;
      const dy = (event.clientY - drag.startY) / display.height;
      const start = drag.box;
      let next: Box = { ...start };
      if (drag.mode === "move") {
        next.x = clamp(start.x + dx, 0, 1 - start.width);
        next.y = clamp(start.y + dy, 0, 1 - start.height);
      } else {
        let left = start.x;
        let top = start.y;
        let right = start.x + start.width;
        let bottom = start.y + start.height;
        if (drag.mode.includes("w")) left = clamp(start.x + dx, 0, right - 0.05);
        if (drag.mode.includes("e")) right = clamp(start.x + start.width + dx, left + 0.05, 1);
        if (drag.mode.includes("n")) top = clamp(start.y + dy, 0, bottom - 0.05);
        if (drag.mode.includes("s")) bottom = clamp(start.y + start.height + dy, top + 0.05, 1);
        next = { x: left, y: top, width: right - left, height: bottom - top };
      }
      setBox(next);
    };
    const up = () => setDrag(null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [drag, display]);

  const startDrag = (event: ReactPointerEvent, mode: DragMode) => {
    event.preventDefault();
    event.stopPropagation();
    setDrag({ mode, startX: event.clientX, startY: event.clientY, box });
  };

  const applyRatio = (id: string, value: number | null) => {
    setRatio(id);
    if (value === null) return;
    const imageRatio = image.width / image.height;
    const targetRatio = value;
    let width = 0.82;
    let height = width * (imageRatio / targetRatio);
    if (height > 0.82) {
      height = 0.82;
      width = height * (targetRatio / imageRatio);
    }
    setBox({ x: (1 - width) / 2, y: (1 - height) / 2, width, height });
  };

  const crop = async () => {
    setBusy(true);
    try {
      const result = await api.cropImage(image.id, box);
      onCropped(result);
      notify("裁切完成", `新图 ${result.width} × ${result.height}`);
      onClose();
    } catch (error) {
      fail(error, "裁切失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="裁切图片"
      eyebrow="EDIT / 本地图像操作"
      width={760}
      footer={
        <>
          <span className="crop-size">
            {pixelWidth} × {pixelHeight} px
          </span>
          <button className="button button-ghost" onClick={onClose}>
            取消
          </button>
          <button className="button button-primary" onClick={() => void crop()} disabled={busy}>
            {busy ? <Loader2 size={15} className="spin" /> : <Crop size={15} />}
            应用裁切
          </button>
        </>
      }
    >
      <div className="crop-dialog">
        <div className="crop-toolbar">
          <span>比例</span>
          <div className="crop-ratios">
            {RATIOS.map((item) => (
              <button
                key={item.id}
                className={cn("crop-ratio", ratio === item.id && "active")}
                onClick={() => applyRatio(item.id, item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button className="text-button" onClick={() => setBox({ x: 0, y: 0, width: 1, height: 1 })}>
            <RotateCcw size={12} /> 全图
          </button>
        </div>

        <div className="crop-stage-wrap">
          <div
            className="crop-stage"
            ref={stageRef}
            style={{ width: display.width, height: display.height }}
            onPointerDown={(event) => startDrag(event, "move")}
          >
            <img src={api.imageUrl(image)} alt={image.prompt} draggable={false} />
            <div
              className="crop-box"
              style={{
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.width * 100}%`,
                height: `${box.height * 100}%`,
              }}
              onPointerDown={(event) => startDrag(event, "move")}
            >
              <span className="crop-grid-line vertical one" />
              <span className="crop-grid-line vertical two" />
              <span className="crop-grid-line horizontal one" />
              <span className="crop-grid-line horizontal two" />
              <span className="crop-handle nw" onPointerDown={(event) => startDrag(event, "nw")} />
              <span className="crop-handle ne" onPointerDown={(event) => startDrag(event, "ne")} />
              <span className="crop-handle sw" onPointerDown={(event) => startDrag(event, "sw")} />
              <span className="crop-handle se" onPointerDown={(event) => startDrag(event, "se")} />
            </div>
          </div>
        </div>
        <p className="crop-note">拖动边框移动裁切区域，拖拽四角调整大小。裁切生成新作品，原图保持不变。</p>
      </div>
    </Modal>
  );
}
