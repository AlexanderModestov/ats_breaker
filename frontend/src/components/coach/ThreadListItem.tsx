"use client";

import { useState } from "react";
import { MoreVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CoachSession } from "@/types";

interface Props {
  session: CoachSession;
  active: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => void;
  onDelete: () => void;
}

function displayTitle(s: CoachSession): string {
  if (s.title) return s.title;
  if (s.preview) return s.preview.slice(0, 40);
  return "New thread";
}

export function ThreadListItem({ session, active, onSelect, onRename, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.title ?? "");
  const [menuOpen, setMenuOpen] = useState(false);

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (draft.trim() && draft !== (session.title ?? "")) onRename(draft.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(session.title ?? "");
            setEditing(false);
          }
        }}
        className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
      />
    );
  }

  return (
    <div
      className={cn(
        "group flex items-center justify-between rounded-md px-2 py-1.5 text-sm cursor-pointer",
        active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
      )}
      onClick={onSelect}
    >
      <span className="truncate flex-1">{displayTitle(session)}</span>
      <div className="relative">
        <button
          type="button"
          className="opacity-0 group-hover:opacity-100 p-1"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((v) => !v);
          }}
          aria-label="Thread actions"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-7 z-10 w-32 rounded-md border border-border bg-popover shadow-md text-sm">
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-muted"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                setEditing(true);
              }}
            >
              Rename
            </button>
            <button
              className="w-full px-3 py-1.5 text-left text-destructive hover:bg-muted"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                if (session.message_count === 0 || confirm("Delete thread?")) onDelete();
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
