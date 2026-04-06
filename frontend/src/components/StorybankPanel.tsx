"use client";

import { useState } from "react";
import {
  BookOpen,
  ChevronRight,
  Pencil,
  Trash2,
  X,
  Check,
  Star,
} from "lucide-react";
import { motion, AnimatePresence } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useStorybank, useUpdateStory, useDeleteStory } from "@/hooks/useStorybank";
import type { StorybankEntry, StorybankEntryRequest } from "@/types";
import { cn } from "@/lib/utils";

interface StorybankPanelProps {
  collapsed: boolean;
  onToggle: () => void;
}

/* ------------------------------------------------------------------ */
/*  StoryCard (internal sub-component)                                 */
/* ------------------------------------------------------------------ */

interface StoryCardProps {
  entry: StorybankEntry;
}

function StoryCard({ entry }: StoryCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);

  const updateStory = useUpdateStory();
  const deleteStory = useDeleteStory();

  // Edit form state
  const [form, setForm] = useState<StorybankEntryRequest>({
    title: entry.title,
    situation: entry.situation,
    task: entry.task,
    action: entry.action,
    result: entry.result,
    tags: entry.tags,
    rating: entry.rating,
  });
  const [tagsInput, setTagsInput] = useState(entry.tags.join(", "));

  function startEdit() {
    setForm({
      title: entry.title,
      situation: entry.situation,
      task: entry.task,
      action: entry.action,
      result: entry.result,
      tags: entry.tags,
      rating: entry.rating,
    });
    setTagsInput(entry.tags.join(", "));
    setEditing(true);
    setExpanded(true);
  }

  function cancelEdit() {
    setEditing(false);
  }

  function saveEdit() {
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    updateStory.mutate(
      { id: entry.id, data: { ...form, tags } },
      { onSuccess: () => setEditing(false) },
    );
  }

  function handleDelete() {
    deleteStory.mutate(entry.id);
  }

  const TAG_COLORS = [
    "bg-blue-500/15 text-blue-700 dark:text-blue-300",
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    "bg-purple-500/15 text-purple-700 dark:text-purple-300",
    "bg-rose-500/15 text-rose-700 dark:text-rose-300",
    "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
  ];

  function tagColor(index: number) {
    return TAG_COLORS[index % TAG_COLORS.length];
  }

  /* ---------- editing mode ---------- */
  if (editing) {
    return (
      <motion.div
        layout
        className="rounded-lg border border-border bg-card p-4 space-y-3"
      >
        {/* Title */}
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          placeholder="Title"
        />

        {/* S / T / A / R textareas */}
        {(["situation", "task", "action", "result"] as const).map((field) => (
          <div key={field}>
            <label className="mb-1 block text-xs font-medium uppercase text-muted-foreground">
              {field}
            </label>
            <textarea
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
              rows={2}
              value={(form[field] as string) ?? ""}
              onChange={(e) => setForm({ ...form, [field]: e.target.value })}
            />
          </div>
        ))}

        {/* Tags */}
        <div>
          <label className="mb-1 block text-xs font-medium uppercase text-muted-foreground">
            Tags (comma-separated)
          </label>
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="leadership, python, teamwork"
          />
        </div>

        {/* Buttons */}
        <div className="flex items-center justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={cancelEdit}>
            <X className="mr-1 h-3.5 w-3.5" />
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={saveEdit}
            disabled={updateStory.isPending}
          >
            <Check className="mr-1 h-3.5 w-3.5" />
            Save
          </Button>
        </div>
      </motion.div>
    );
  }

  /* ---------- read mode ---------- */
  return (
    <motion.div
      layout
      whileHover={{ y: -1 }}
      transition={{ duration: 0.2 }}
      className="rounded-lg border border-border bg-card transition-colors hover:border-border/80"
    >
      {/* Header row */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ duration: 0.2 }}
          className="shrink-0 text-muted-foreground"
        >
          <ChevronRight className="h-4 w-4" />
        </motion.span>

        <span className="flex-1 truncate text-sm font-medium text-foreground">
          {entry.title}
        </span>

        {entry.rating !== null && (
          <span className="flex items-center gap-0.5 text-xs text-amber-500">
            <Star className="h-3.5 w-3.5 fill-current" />
            {entry.rating}
          </span>
        )}
      </button>

      {/* Tags */}
      {entry.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2">
          {entry.tags.map((tag, i) => (
            <Badge
              key={tag}
              variant="secondary"
              className={cn("text-[10px] font-normal", tagColor(i))}
            >
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {/* Expanded S/T/A/R content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="space-y-2 border-t border-border px-4 py-3">
              {(["situation", "task", "action", "result"] as const).map(
                (field) =>
                  entry[field] && (
                    <div key={field}>
                      <span className="text-[10px] font-semibold uppercase text-muted-foreground">
                        {field}
                      </span>
                      <p className="text-sm text-foreground/90">
                        {entry[field]}
                      </p>
                    </div>
                  ),
              )}

              {/* Action buttons */}
              <div className="flex items-center justify-end gap-1 pt-1">
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={startEdit}>
                  <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 hover:text-destructive"
                  onClick={handleDelete}
                  disabled={deleteStory.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  StorybankPanel                                                      */
/* ------------------------------------------------------------------ */

export function StorybankPanel({ collapsed, onToggle }: StorybankPanelProps) {
  const { data: stories = [], isLoading } = useStorybank();

  /* ---------- collapsed: floating button ---------- */
  if (collapsed) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2 }}
        className="fixed right-4 top-20 z-40"
      >
        <Button
          size="icon"
          variant="outline"
          className="h-10 w-10 rounded-full shadow-md"
          onClick={onToggle}
        >
          <BookOpen className="h-5 w-5" />
        </Button>
      </motion.div>
    );
  }

  /* ---------- expanded panel ---------- */
  return (
    <motion.aside
      initial={{ x: 80, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 80, opacity: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="flex h-full w-80 shrink-0 flex-col border-l border-border bg-background"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold text-foreground">Storybank</h2>
          <Badge variant="secondary" className="text-[10px] font-normal">
            {stories.length}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onToggle}>
          <X className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <span className="text-sm text-muted-foreground">Loading...</span>
          </div>
        ) : stories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <BookOpen className="mb-3 h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              No stories yet. Chat with the career coach to build your storybank.
            </p>
          </div>
        ) : (
          stories.map((entry) => <StoryCard key={entry.id} entry={entry} />)
        )}
      </div>
    </motion.aside>
  );
}
