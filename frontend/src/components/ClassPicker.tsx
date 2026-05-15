import { classColor } from "../classColor";

interface Props {
  classNames: string[];
  activeIdx: number;
  onSelect: (idx: number) => void;
}

export function ClassPicker({ classNames, activeIdx, onSelect }: Props) {
  if (classNames.length === 0) return null;
  return (
    <div className="section">
      <h3>Active class</h3>
      <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
        {classNames.map((name, i) => {
          const active = i === activeIdx;
          const color = classColor(i);
          return (
            <button
              key={`${i}-${name}`}
              type="button"
              className="ghost"
              onClick={() => onSelect(i)}
              title={`${name} (press ${i + 1 <= 9 ? i + 1 : ""})`}
              style={{
                padding: "4px 8px",
                borderColor: active ? color : "var(--border)",
                background: active ? `${color}26` : "transparent",
                color: active ? color : "var(--text)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
              }}
            >
              <span
                aria-hidden
                style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: color,
                }}
              />
              {i + 1 <= 9 && <span className="kbd">{i + 1}</span>}
              {name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
