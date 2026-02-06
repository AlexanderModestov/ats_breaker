"use client";

import { useState } from "react";
import { Link, FileText, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { motion, AnimatePresence } from "@/components/motion";
import { cn } from "@/lib/utils";

interface JobInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function JobInput({ value, onChange, disabled }: JobInputProps) {
  const [mode, setMode] = useState<"url" | "text">("url");

  const isUrl = value.startsWith("http://") || value.startsWith("https://");

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="inline-flex rounded-lg bg-secondary/50 p-1">
        <button
          type="button"
          onClick={() => setMode("url")}
          disabled={disabled}
          className={cn(
            "relative inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            mode === "url" ? "text-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {mode === "url" && (
            <motion.div
              layoutId="job-input-mode"
              className="absolute inset-0 rounded-md bg-background shadow-sm"
              transition={{ type: "spring", stiffness: 500, damping: 40 }}
            />
          )}
          <span className="relative z-10 flex items-center gap-2">
            <Link className="h-4 w-4" />
            URL
          </span>
        </button>
        <button
          type="button"
          onClick={() => setMode("text")}
          disabled={disabled}
          className={cn(
            "relative inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            mode === "text" ? "text-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {mode === "text" && (
            <motion.div
              layoutId="job-input-mode"
              className="absolute inset-0 rounded-md bg-background shadow-sm"
              transition={{ type: "spring", stiffness: 500, damping: 40 }}
            />
          )}
          <span className="relative z-10 flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Paste Text
          </span>
        </button>
      </div>

      {/* Input area */}
      <AnimatePresence mode="wait">
        {mode === "url" ? (
          <motion.div
            key="url"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.15 }}
          >
            <Input
              placeholder="https://example.com/job/12345"
              value={isUrl || value === "" ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              className="h-12 text-base"
            />
          </motion.div>
        ) : (
          <motion.div
            key="text"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.15 }}
          >
            <textarea
              className="flex min-h-[140px] w-full rounded-xl border border-input bg-background px-4 py-3 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Paste the job posting text here..."
              value={!isUrl ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status indicator */}
      <AnimatePresence>
        {value && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <Check className="h-4 w-4 text-green-600" />
            {isUrl ? (
              <span>Job URL provided</span>
            ) : (
              <span>{value.length.toLocaleString()} characters</span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
