"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";
import {
  useImportStatus,
  getPendingImport,
  clearPendingImport,
} from "@/lib/hooks/use-import-status";

export function ImportStatusNotifier() {
  const router = useRouter();
  const { data: session } = useSession();
  const [pendingImport, setPendingImport] = useState<{
    importId: string;
    userId: string;
  } | null>(null);

  useEffect(() => {
    if (!session?.user?.id) return;
    const stored = getPendingImport();
    if (!stored) return;
    if (stored.userId !== session.user.id) {
      clearPendingImport();
      return;
    }
    setPendingImport(stored);
  }, [session?.user?.id]);

  useImportStatus(pendingImport?.userId, pendingImport?.importId, {
    showToasts: true,
    onCompleted: () => {
      clearPendingImport();
      setPendingImport(null);
      router.refresh();
    },
    onFailed: () => {
      clearPendingImport();
      setPendingImport(null);
    },
  });

  return null;
}
