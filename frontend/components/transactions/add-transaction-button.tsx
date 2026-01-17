"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { RiAddLine, RiEditLine, RiUploadCloud2Line } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { hasOpenAiApiKey } from "@/lib/actions/settings";

interface AddTransactionButtonProps {
  onAddManual: () => void;
}

export function AddTransactionButton({ onAddManual }: AddTransactionButtonProps) {
  const router = useRouter();
  const [showCsvOption, setShowCsvOption] = useState(false);

  useEffect(() => {
    const checkApiKey = async () => {
      const hasKey = await hasOpenAiApiKey();
      setShowCsvOption(hasKey);
    };
    checkApiKey();
  }, []);

  const handleCsvImport = () => {
    router.push("/transactions/import");
  };

  // If CSV option is not available, show a simple button
  if (!showCsvOption) {
    return (
      <Button onClick={onAddManual}>
        <RiAddLine className="mr-2 h-4 w-4" />
        Add Transaction
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button>
          <RiAddLine className="mr-2 h-4 w-4" />
          Add Transaction
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onAddManual}>
          <RiEditLine className="mr-2 h-4 w-4" />
          Add Manually
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCsvImport}>
          <RiUploadCloud2Line className="mr-2 h-4 w-4" />
          Import from CSV
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
