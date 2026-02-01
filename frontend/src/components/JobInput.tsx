"use client";

import { useState } from "react";
import { Link, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface JobInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function JobInput({ value, onChange, disabled }: JobInputProps) {
  const [mode, setMode] = useState<"url" | "text">("url");

  const isUrl = value.startsWith("http://") || value.startsWith("https://");

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Button
          variant={mode === "url" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("url")}
          disabled={disabled}
        >
          <Link className="mr-1 h-4 w-4" />
          URL
        </Button>
        <Button
          variant={mode === "text" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("text")}
          disabled={disabled}
        >
          <FileText className="mr-1 h-4 w-4" />
          Paste Text
        </Button>
      </div>

      {mode === "url" ? (
        <Input
          placeholder="https://example.com/job/12345"
          value={isUrl || value === "" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      ) : (
        <textarea
          className="flex min-h-[120px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          placeholder="Paste the job posting text here..."
          value={!isUrl ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      )}

      {value && (
        <p className="text-xs text-muted-foreground">
          {isUrl ? "Job URL provided" : `${value.length} characters`}
        </p>
      )}
    </div>
  );
}
