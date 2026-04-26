import { Skeleton } from "@/components/ui/skeleton";

export function HeaderSkeleton({ title }: { title: string }) {
  return (
    <div className="flex h-16 items-center gap-2 border-b px-4">
      <Skeleton className="h-5 w-5" />
      <span className="text-base font-medium">{title}</span>
    </div>
  );
}

export function TableSkeleton({ rows = 12 }: { rows?: number }) {
  return (
    <div className="flex flex-1 flex-col gap-2">
      <div className="flex gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-9 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function FiltersSkeleton() {
  return (
    <div className="flex gap-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-32" />
      ))}
    </div>
  );
}

export function CardGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-28 w-full" />
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 320 }: { height?: number }) {
  return <Skeleton className="w-full" style={{ height }} />;
}

export function DetailListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
