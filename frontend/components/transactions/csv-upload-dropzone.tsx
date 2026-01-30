"use client";

import { useState, useCallback } from "react";
import { RiUploadCloud2Line, RiFileTextLine, RiCloseLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import * as XLSX from "xlsx";

interface CsvUploadDropzoneProps {
  onFileSelect: (file: File, content: string) => void;
  isUploading?: boolean;
}

// Supported file extensions and MIME types
const VALID_EXTENSIONS = [".csv", ".xls", ".xlsx"];
const VALID_TYPES = [
  "text/csv",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];

export function CsvUploadDropzone({ onFileSelect, isUploading }: CsvUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const processFile = useCallback(
    async (file: File) => {
      setError(null);

      // Validate file type
      const extension = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
      const isValidExtension = VALID_EXTENSIONS.includes(extension);
      const isValidType = VALID_TYPES.includes(file.type) || file.type === "";

      if (!isValidExtension && !isValidType) {
        setError("Please upload a CSV or Excel file");
        return;
      }

      // Validate file size (max 10MB)
      if (file.size > 10 * 1024 * 1024) {
        setError("File size must be less than 10MB");
        return;
      }

      setSelectedFile(file);

      try {
        // Check if it's an Excel file
        if (file.name.match(/\.xlsx?$/i)) {
          // Excel file - parse with xlsx library
          const arrayBuffer = await file.arrayBuffer();
          const workbook = XLSX.read(arrayBuffer, { type: "array" });
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
          const csvContent = XLSX.utils.sheet_to_csv(firstSheet);
          onFileSelect(file, csvContent);
        } else {
          // CSV - read as text
          const reader = new FileReader();
          reader.onload = (e) => {
            const content = e.target?.result as string;
            onFileSelect(file, content);
          };
          reader.onerror = () => {
            setError("Failed to read file");
          };
          reader.readAsText(file);
        }
      } catch {
        setError("Failed to read file");
      }
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files?.[0];
      if (file) {
        processFile(file);
      }
    },
    [processFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        processFile(file);
      }
    },
    [processFile]
  );

  const handleRemove = () => {
    setSelectedFile(null);
    setError(null);
  };

  if (selectedFile) {
    return (
      <div className="rounded-lg border border-dashed p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <RiFileTextLine className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="font-medium">{selectedFile.name}</p>
              <p className="text-xs text-muted-foreground">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleRemove}
            disabled={isUploading}
          >
            <RiCloseLine className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border-2 border-dashed p-8 text-center transition-colors cursor-pointer",
        isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25",
        error && "border-destructive"
      )}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => document.getElementById("csv-file-input")?.click()}
    >
      <input
        id="csv-file-input"
        type="file"
        accept=".csv,.xls,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="hidden"
        onChange={handleFileInput}
      />
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <RiUploadCloud2Line className="h-8 w-8 text-muted-foreground" />
        </div>
        <div>
          <p className="text-lg font-medium">
            {isDragging ? "Drop your file here" : "Upload your file"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Drag and drop or click to browse
          </p>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <p className="text-xs text-muted-foreground">CSV or Excel (max 10MB)</p>
      </div>
    </div>
  );
}
