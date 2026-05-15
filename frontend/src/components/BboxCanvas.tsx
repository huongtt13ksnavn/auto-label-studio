import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Image as KImage, Rect, Text, Group } from "react-konva";
import Konva from "konva";
import type { Box, ImageRecord } from "../types";
import { classColor, classLabel } from "../classColor";

interface Props {
  image: ImageRecord;
  imageUrl: string;
  boxes: Box[];
  onChange: (boxes: Box[]) => void;
  selectedIdx: number | null;
  setSelectedIdx: (i: number | null) => void;
  classNames: string[];
  activeClassIdx: number;
}

export function BboxCanvas({
  image,
  imageUrl,
  boxes,
  onChange,
  selectedIdx,
  setSelectedIdx,
  classNames,
  activeClassIdx,
}: Props) {
  const stageRef = useRef<Konva.Stage>(null);
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null);
  const [container, setContainer] = useState({ w: 800, h: 600 });
  const wrapRef = useRef<HTMLDivElement>(null);
  const [drawing, setDrawing] = useState<null | {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  }>(null);

  // load image
  useEffect(() => {
    const el = new window.Image();
    el.crossOrigin = "anonymous";
    el.src = imageUrl;
    el.onload = () => setImgEl(el);
  }, [imageUrl]);

  // observe container size
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(() => {
      const r = wrapRef.current!.getBoundingClientRect();
      setContainer({ w: r.width, h: r.height });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // fit image to container
  const scale = imgEl
    ? Math.min(container.w / image.width, container.h / image.height) * 0.95
    : 1;
  const drawW = image.width * scale;
  const drawH = image.height * scale;
  const offsetX = (container.w - drawW) / 2;
  const offsetY = (container.h - drawH) / 2;

  // helpers: convert pixel <-> normalized
  const pxToNorm = (px: number, py: number, w: number, h: number) => ({
    cx: (px + w / 2) / drawW,
    cy: (py + h / 2) / drawH,
    w: w / drawW,
    h: h / drawH,
  });

  const handleMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (!imgEl) return;
    const pos = stageRef.current!.getPointerPosition();
    if (!pos) return;
    const x = pos.x - offsetX;
    const y = pos.y - offsetY;
    if (x < 0 || y < 0 || x > drawW || y > drawH) return;

    // start new bbox
    setDrawing({ x0: x, y0: y, x1: x, y1: y });
    setSelectedIdx(null);
  };

  const handleMouseMove = () => {
    if (!drawing) return;
    const pos = stageRef.current!.getPointerPosition();
    if (!pos) return;
    const x = Math.max(0, Math.min(drawW, pos.x - offsetX));
    const y = Math.max(0, Math.min(drawH, pos.y - offsetY));
    setDrawing({ ...drawing, x1: x, y1: y });
  };

  const handleMouseUp = () => {
    if (!drawing) return;
    const x = Math.min(drawing.x0, drawing.x1);
    const y = Math.min(drawing.y0, drawing.y1);
    const w = Math.abs(drawing.x1 - drawing.x0);
    const h = Math.abs(drawing.y1 - drawing.y0);
    setDrawing(null);
    if (w < 6 || h < 6) return; // ignore tiny

    const norm = pxToNorm(x, y, w, h);
    const next: Box = {
      cx: norm.cx,
      cy: norm.cy,
      w: norm.w,
      h: norm.h,
      class_idx: Math.max(0, Math.min(classNames.length - 1, activeClassIdx)),
      confidence: null,
      source: "human",
    };
    onChange([...boxes, next]);
    setSelectedIdx(boxes.length);
  };

  const deleteBox = (idx: number) => {
    const copy = boxes.slice();
    copy.splice(idx, 1);
    onChange(copy);
    setSelectedIdx(null);
  };

  // keyboard delete on selected
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (selectedIdx === null) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        // don't steal from form fields
        const tag = (e.target as HTMLElement | null)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        e.preventDefault();
        deleteBox(selectedIdx);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIdx, boxes]);

  return (
    <div ref={wrapRef} style={{ width: "100%", height: "100%" }}>
      <Stage
        ref={stageRef}
        width={container.w}
        height={container.h}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{ cursor: drawing ? "crosshair" : "default" }}
      >
        <Layer>
          {imgEl && (
            <KImage
              image={imgEl}
              x={offsetX}
              y={offsetY}
              width={drawW}
              height={drawH}
              listening={false}
            />
          )}

          {boxes.map((b, i) => {
            const x = (b.cx - b.w / 2) * drawW + offsetX;
            const y = (b.cy - b.h / 2) * drawH + offsetY;
            const w = b.w * drawW;
            const h = b.h * drawH;
            const isSelected = i === selectedIdx;
            const color = classColor(b.class_idx);
            const stroke = isSelected ? "#4ed489" : color;
            const dash = b.source === "model" ? [6, 4] : undefined;
            const name = classLabel(b.class_idx, classNames);
            const label =
              b.confidence != null
                ? `${name} ${(b.confidence * 100).toFixed(0)}%`
                : name;
            return (
              <Group key={i} onClick={() => setSelectedIdx(i)}>
                <Rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  stroke={stroke}
                  strokeWidth={isSelected ? 3 : 2}
                  dash={dash}
                  fill="transparent"
                  draggable={isSelected}
                  onDragEnd={(e) => {
                    const node = e.target;
                    const nx = node.x() - offsetX;
                    const ny = node.y() - offsetY;
                    const next = pxToNorm(nx, ny, w, h);
                    const copy = boxes.slice();
                    copy[i] = { ...copy[i], ...next, source: "human" };
                    onChange(copy);
                  }}
                />
                <Text
                  text={label}
                  fontSize={11}
                  fill={stroke}
                  x={x}
                  y={Math.max(0, y - 14)}
                />
              </Group>
            );
          })}

          {drawing && (
            <Rect
              x={Math.min(drawing.x0, drawing.x1) + offsetX}
              y={Math.min(drawing.y0, drawing.y1) + offsetY}
              width={Math.abs(drawing.x1 - drawing.x0)}
              height={Math.abs(drawing.y1 - drawing.y0)}
              stroke="#4ed489"
              strokeWidth={1}
              dash={[4, 4]}
            />
          )}
        </Layer>
      </Stage>
    </div>
  );
}
