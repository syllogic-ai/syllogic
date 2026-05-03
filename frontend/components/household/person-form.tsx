"use client";

import { useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { PersonAvatar } from "./person-avatar";

const COLORS = ["#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"];
const MAX_BYTES = 2 * 1024 * 1024;

export type PersonFormValues = {
  name: string;
  color: string;
  avatar?: File;       // present when user picked a new file
  clearAvatar?: boolean; // true when user explicitly removed the existing avatar
};

export function PersonForm(props: {
  initial?: { name: string; color?: string | null; avatarUrl?: string | null };
  submitLabel: string;
  onSubmit: (values: PersonFormValues) => Promise<void>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(props.initial?.name ?? "");
  const [color, setColor] = useState(props.initial?.color ?? COLORS[0]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(props.initial?.avatarUrl ?? null);
  const [pickedFile, setPickedFile] = useState<File | undefined>();
  const [cleared, setCleared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function onFile(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("Image too large (max 2 MB)");
      return;
    }
    if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type)) {
      setError("Unsupported image type");
      return;
    }
    setPickedFile(file);
    setCleared(false);
    setPreviewUrl(URL.createObjectURL(file));
  }

  function clearAvatar() {
    setPickedFile(undefined);
    setPreviewUrl(null);
    setCleared(true);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await props.onSubmit({
            name: name.trim(),
            color: color ?? COLORS[0]!,
            avatar: pickedFile,
            clearAvatar: cleared,
          });
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="flex items-center gap-4">
        <PersonAvatar
          person={{ id: "preview", name: name || "?", color, avatarUrl: previewUrl }}
          size={56}
        />
        <div className="flex flex-col gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileRef.current?.click()}
          >
            {previewUrl ? "Change photo" : "Upload photo"}
          </Button>
          {previewUrl && (
            <Button type="button" variant="ghost" size="sm" onClick={clearAvatar}>
              Remove photo
            </Button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div>
        <Label>Name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} />
      </div>

      <div>
        <Label>Color (used as fallback when no photo)</Label>
        <div className="flex gap-2 mt-1">
          {COLORS.map((c) => (
            <button
              type="button"
              key={c}
              aria-label={`color ${c}`}
              onClick={() => setColor(c)}
              className="h-7 w-7 rounded-full ring-offset-2"
              style={{
                background: c,
                outline: c === color ? "2px solid black" : "none",
              }}
            />
          ))}
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        {props.onCancel && (
          <Button type="button" variant="ghost" onClick={props.onCancel} disabled={busy}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={busy || name.trim().length === 0}>
          {props.submitLabel}
        </Button>
      </div>
    </form>
  );
}
