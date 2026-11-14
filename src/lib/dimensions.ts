export interface ComputedSize {
  width: number;
  height: number;
  megapixels: number;
}

const RATIOS: Record<string, number> = {
  "1:1": 1,
  "4:3": 4 / 3,
  "3:4": 3 / 4,
  "3:2": 3 / 2,
  "2:3": 2 / 3,
  "16:9": 16 / 9,
  "9:16": 9 / 16,
  "21:9": 21 / 9,
};

export function computeSize(aspect: string, longEdge: number, maxPixels = 4_194_304): ComputedSize {
  const ratio = RATIOS[aspect] ?? 1;
  const edge = Math.max(256, Math.min(2048, longEdge));
  let width = ratio >= 1 ? edge : edge * ratio;
  let height = ratio >= 1 ? edge / ratio : edge;
  if (width * height > maxPixels) {
    const scale = Math.sqrt(maxPixels / (width * height));
    width *= scale;
    height *= scale;
  }
  width = Math.max(256, Math.round(width / 16) * 16);
  height = Math.max(256, Math.round(height / 16) * 16);
  return { width, height, megapixels: Number(((width * height) / 1_000_000).toFixed(2)) };
}

export function ratioForAspect(aspect: string): number {
  return RATIOS[aspect] ?? 1;
}
