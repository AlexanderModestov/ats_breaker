"use client";
import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

interface EditPopupProps {
  text: string;
  position: { top: number; left: number };
  onSave: (newText: string) => void;
  onCancel: () => void;
}

export default function EditPopup({
  text,
  position,
  onSave,
  onCancel,
}: EditPopupProps) {
  const [value, setValue] = useState(text);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
    textareaRef.current?.select();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onCancel();
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      onSave(value);
    }
  };

  return (
    <div
      className="fixed z-50 bg-popover border rounded-lg shadow-lg p-3 w-80"
      style={{ top: position.top, left: position.left }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="w-full min-h-[80px] resize-y rounded border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        placeholder="Edit text..."
      />
      <div className="flex justify-end gap-2 mt-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => onSave(value)}>
          Save
        </Button>
      </div>
      <p className="text-xs text-muted-foreground mt-1">
        Ctrl+Enter to save, Esc to cancel
      </p>
    </div>
  );
}
