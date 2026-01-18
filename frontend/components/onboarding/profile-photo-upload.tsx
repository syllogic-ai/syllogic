"use client";

import { useState, useRef, useCallback } from "react";
import { RiCameraLine, RiCloseLine } from "@remixicon/react";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ProfilePhotoUploadProps {
  value?: File | null;
  onChange: (file: File | null) => void;
  defaultImage?: string | null;
  name?: string;
}

export function ProfilePhotoUpload({
  value,
  onChange,
  defaultImage,
  name,
}: ProfilePhotoUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback(
    (file: File | null) => {
      if (file) {
        const reader = new FileReader();
        reader.onloadend = () => {
          setPreview(reader.result as string);
        };
        reader.readAsDataURL(file);
        onChange(file);
      } else {
        setPreview(null);
        onChange(null);
      }
    },
    [onChange]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    handleFileChange(file);
  };

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file && file.type.startsWith("image/")) {
        handleFileChange(file);
      }
    },
    [handleFileChange]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleRemove = () => {
    handleFileChange(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const getInitials = (name?: string) => {
    if (!name) return "?";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const displayImage = preview || defaultImage;

  return (
    <div className="flex flex-col items-center gap-4">
      <div
        className={cn(
          "relative cursor-pointer transition-all",
          isDragging && "ring-2 ring-primary ring-offset-2"
        )}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
      >
        <Avatar className="h-24 w-24">
          {displayImage ? (
            <AvatarImage src={displayImage} alt="Profile photo" />
          ) : (
            <AvatarFallback className="text-2xl">{getInitials(name)}</AvatarFallback>
          )}
        </Avatar>
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity hover:opacity-100">
          <RiCameraLine className="h-6 w-6 text-white" />
        </div>
        {displayImage && (
          <Button
            type="button"
            variant="destructive"
            size="icon"
            className="absolute -right-1 -top-1 h-6 w-6 rounded-full"
            onClick={(e) => {
              e.stopPropagation();
              handleRemove();
            }}
          >
            <RiCloseLine className="h-4 w-4" />
          </Button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleInputChange}
      />
      <p className="text-xs text-muted-foreground">
        Click or drag to upload a profile photo
      </p>
    </div>
  );
}
