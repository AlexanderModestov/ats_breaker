import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Trigger a browser download for a blob via a temporary anchor.
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Shared className for amber "missing field" edit buttons (compact size).
// Use cn(AMBER_FIELD_BTN, "text-base") to bump the text size.
export const AMBER_FIELD_BTN =
  "inline-flex items-center gap-1.5 rounded-md border border-dashed border-amber-400 px-2 py-0.5 text-sm font-medium text-amber-700 transition-colors hover:border-solid hover:bg-amber-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 dark:border-amber-500/60 dark:text-amber-400 dark:hover:bg-amber-950/30";
