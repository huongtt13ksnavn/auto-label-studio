// Distinct hues cycled by class index. Picked for contrast on a dark canvas
// and to stay visually distinguishable up to ~12 classes; beyond that they
// repeat with the same hue (callers should accept ambiguity past 12).
const HUES = [210, 30, 140, 320, 50, 270, 0, 180, 100, 250, 20, 160];

export function classColor(idx: number): string {
  const h = HUES[((idx % HUES.length) + HUES.length) % HUES.length];
  return `hsl(${h}, 70%, 60%)`;
}

export function classLabel(idx: number, names: string[]): string {
  return names[idx] ?? `class ${idx}`;
}
