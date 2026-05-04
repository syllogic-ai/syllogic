"use client";

import { useState } from "react";
import { PersonFilter } from "@/components/dashboard/person-filter";

export function InvestmentsPersonFilterBar() {
  const [selectedPersonIds, setSelectedPersonIds] = useState<string[]>([]);

  return (
    <div>
      <PersonFilter value={selectedPersonIds} onChange={setSelectedPersonIds} />
      {/* TODO(person-filter): wire to data once MCP/Drizzle queries accept personIds */}
    </div>
  );
}
