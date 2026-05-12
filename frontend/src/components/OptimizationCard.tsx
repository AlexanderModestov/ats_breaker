"use client";

import { useState } from "react";
import {
  Building2,
  Clock,
  ExternalLink,
  ArrowRight,
  Trash2,
  Plus,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InlineEdit } from "@/components/InlineEdit";
import { motion } from "@/components/motion";
import { useUpdateOptimizationJob } from "@/hooks/useOptimization";
import type { OptimizationSummary } from "@/types";

interface OptimizationCardProps {
  optimization: OptimizationSummary;
  onClick: () => void;
  onDelete?: (id: string) => void;
  isDeleting?: boolean;
}

type EditingField = "title" | "company" | null;

export function OptimizationCard({
  optimization,
  onClick,
  onDelete,
  isDeleting,
}: OptimizationCardProps) {
  const [editing, setEditing] = useState<EditingField>(null);
  const [localOpt, setLocalOpt] = useState<OptimizationSummary | null>(null);
  const update = useUpdateOptimizationJob(optimization.id);

  const opt = localOpt ?? optimization;
  const needsReview = new Set(opt.needs_review ?? []);
  const titleMissing = needsReview.has("title");
  const companyMissing = needsReview.has("company");

  const saveField = async (field: "title" | "company", newText: string) => {
    const trimmed = newText.trim();
    if (!trimmed) {
      setEditing(null);
      return;
    }
    try {
      const updated = await update.mutateAsync({ [field]: trimmed });
      const updatedJob = updated.job_parsed;
      if (updatedJob) {
        setLocalOpt({
          ...opt,
          job_title: updatedJob.title,
          job_company: updatedJob.company,
          needs_review: updatedJob.needs_review ?? [],
        });
      }
    } catch (err) {
      console.error("Failed to save optimization edit:", err);
    } finally {
      setEditing(null);
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && !isDeleting) {
      onDelete(opt.id);
    }
  };

  const handleCardClick = () => {
    if (editing) return;
    onClick();
  };

  const formattedDate = new Date(opt.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  const getDisplayUrl = (url: string | null) => {
    if (!url) return null;
    try {
      const parsed = new URL(url);
      return parsed.hostname.replace("www.", "");
    } catch {
      return url;
    }
  };

  const displayUrl = getDisplayUrl(opt.job_url);

  return (
    <motion.div
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.2 }}
    >
      <Card
        className="group cursor-pointer transition-all duration-200 hover:shadow-md"
        onClick={handleCardClick}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="line-clamp-1 text-base font-medium">
              {editing === "title" ? (
                <InlineEdit
                  initial=""
                  placeholder="Enter position"
                  className="w-full bg-transparent border-b border-input px-0 py-0 text-base font-medium focus:outline-none focus:border-ring"
                  onSave={(v) => saveField("title", v)}
                  onCancel={() => setEditing(null)}
                />
              ) : titleMissing ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditing("title");
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-amber-400 px-2 py-0.5 text-base font-medium text-amber-700 transition-colors hover:border-solid hover:bg-amber-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 dark:border-amber-500/60 dark:text-amber-400 dark:hover:bg-amber-950/30"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  Add position
                </button>
              ) : (
                opt.job_title || "Untitled Job"
              )}
            </CardTitle>
            {onDelete && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
          <CardDescription className="flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5" />
            {editing === "company" ? (
              <InlineEdit
                initial=""
                placeholder="Enter company"
                className="w-full bg-transparent border-b border-input px-0 py-0 text-sm focus:outline-none focus:border-ring"
                onSave={(v) => saveField("company", v)}
                onCancel={() => setEditing(null)}
              />
            ) : companyMissing ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setEditing("company");
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-amber-400 px-2 py-0.5 text-sm font-medium text-amber-700 transition-colors hover:border-solid hover:bg-amber-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 dark:border-amber-500/60 dark:text-amber-400 dark:hover:bg-amber-950/30"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                Add company
              </button>
            ) : (
              <span className="line-clamp-1">
                {opt.job_company || "Unknown Company"}
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                {formattedDate}
              </div>
              {displayUrl && (
                <div className="flex items-center gap-1 truncate max-w-[120px]">
                  <ExternalLink className="h-3 w-3 shrink-0" />
                  <span className="truncate">{displayUrl}</span>
                </div>
              )}
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground/50 transition-transform group-hover:translate-x-1 group-hover:text-primary" />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
