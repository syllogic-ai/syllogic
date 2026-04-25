"use client";

export function AllocationChart({
  allocation,
}: {
  allocation: Record<string, string>;
}) {
  const total = Object.values(allocation).reduce(
    (s, v) => s + Number(v),
    0,
  );
  return (
    <ul className="space-y-1 text-sm">
      {Object.entries(allocation).map(([k, v]) => {
        const pct = total ? (Number(v) / total) * 100 : 0;
        return (
          <li key={k} className="flex justify-between gap-2">
            <span className="capitalize">{k}</span>
            <span>
              {pct.toFixed(1)}% · {v}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
