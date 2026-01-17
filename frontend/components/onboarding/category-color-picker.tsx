"use client";

import { cn } from "@/lib/utils";
import { CATEGORY_COLORS } from "@/lib/constants";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";

interface CategoryColorPickerProps {
  value: string;
  onChange: (color: string) => void;
}

export function CategoryColorPicker({ value, onChange }: CategoryColorPickerProps) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="outline"
            className="h-8 w-8 p-0"
          >
            <div
              className="h-5 w-5 rounded-full"
              style={{ backgroundColor: value }}
            />
          </Button>
        }
      />
      <PopoverContent className="w-auto p-3" align="start">
        <div className="grid grid-cols-4 gap-2">
          {CATEGORY_COLORS.map((color) => (
            <button
              key={color.value}
              type="button"
              className={cn(
                "h-8 w-8 rounded-full transition-transform hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2",
                value === color.value && "ring-2 ring-offset-2 ring-primary"
              )}
              style={{ backgroundColor: color.value }}
              onClick={() => onChange(color.value)}
              title={color.name}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
