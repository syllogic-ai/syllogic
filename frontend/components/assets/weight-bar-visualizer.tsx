"use client";

interface WeightBarVisualizerProps {
  percentage: number;
  color: string;
}

export function WeightBarVisualizer({ percentage, color }: WeightBarVisualizerProps) {
  const totalBars = 10;
  const filledBars = Math.round((percentage / 100) * totalBars);

  return (
    <div className="flex items-end gap-[2px]">
      {[...Array(totalBars)].map((_, i) => (
        <div
          key={i}
          className="w-[3px] h-[12px]"
          style={{
            backgroundColor: i < filledBars ? color : "var(--muted)",
          }}
        />
      ))}
    </div>
  );
}
