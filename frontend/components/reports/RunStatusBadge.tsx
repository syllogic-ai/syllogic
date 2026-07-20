import type { ReportRunStatus } from "@/lib/reports/types";
import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

const VARIANTS: Record<ReportRunStatus, BadgeVariant> = {
  SCHEDULED: "secondary",
  RUNNING: "outline",
  SUCCEEDED: "default",
  FAILED: "destructive",
};

export function RunStatusBadge({ status }: { status: ReportRunStatus }) {
  return <Badge variant={VARIANTS[status]}>{status}</Badge>;
}
