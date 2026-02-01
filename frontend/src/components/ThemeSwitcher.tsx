"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Theme } from "@/types";

interface ThemeSwitcherProps {
  value: Theme;
  onChange: (theme: Theme) => void;
}

const THEMES: { value: Theme; label: string; description: string }[] = [
  {
    value: "minimal",
    label: "Minimal",
    description: "Clean, whitespace-focused",
  },
  {
    value: "professional",
    label: "Professional",
    description: "Blue accents, subtle depth",
  },
  { value: "bold", label: "Bold", description: "Dark mode, vibrant accents" },
];

export function ThemeSwitcher({ value, onChange }: ThemeSwitcherProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) {
      document.documentElement.setAttribute("data-theme", value);
    }
  }, [value, mounted]);

  if (!mounted) {
    return null;
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {THEMES.map((theme) => (
        <button
          key={theme.value}
          onClick={() => onChange(theme.value)}
          className={cn(
            "relative flex flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors hover:border-primary",
            value === theme.value && "border-primary bg-primary/5"
          )}
        >
          {value === theme.value && (
            <Check className="absolute right-3 top-3 h-4 w-4 text-primary" />
          )}
          <span className="font-medium">{theme.label}</span>
          <span className="text-xs text-muted-foreground">
            {theme.description}
          </span>
        </button>
      ))}
    </div>
  );
}
