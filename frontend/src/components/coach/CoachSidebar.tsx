"use client";

import { useMemo, useState } from "react";
import { Plus, ChevronDown, ChevronRight, Lock } from "lucide-react";
import { ThreadListItem } from "./ThreadListItem";
import type { CoachSession, OptimizationSummary } from "@/types";
import { cn } from "@/lib/utils";
import { useSubscription, useCheckout } from "@/hooks/useSubscription";

interface Props {
  sessions: CoachSession[];
  positions: OptimizationSummary[];
  activeThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onCreateThreadInPosition: (optimizationRunId: string) => void;
  onAddPosition: () => void;
  onRenameThread: (threadId: string, title: string) => void;
  onDeleteThread: (threadId: string) => void;
}

export function CoachSidebar({
  sessions,
  positions,
  activeThreadId,
  onSelectThread,
  onCreateThreadInPosition,
  onAddPosition,
  onRenameThread,
  onDeleteThread,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const { data: sub } = useSubscription();
  const isTrialUser = sub?.coach != null && !sub.coach.is_unlimited;
  const threadsRemaining = sub?.coach?.threads_remaining ?? null;
  const atThreadCap = isTrialUser && threadsRemaining === 0;
  const checkout = useCheckout();

  const groups = useMemo(() => {
    const positionsById = new Map(positions.map((p) => [p.id, p]));
    const map = new Map<string, { position: OptimizationSummary | null; threads: CoachSession[] }>();
    for (const s of sessions) {
      if (search) {
        const t = (s.title ?? s.preview ?? "").toLowerCase();
        if (!t.includes(search.toLowerCase())) continue;
      }
      const existing = map.get(s.optimization_run_id) ?? {
        position: positionsById.get(s.optimization_run_id) ?? null,
        threads: [],
      };
      existing.threads.push(s);
      map.set(s.optimization_run_id, existing);
    }
    // Sort threads within each group: nulls first, then last_message_at desc.
    for (const g of map.values()) {
      g.threads.sort((a, b) => {
        if (a.last_message_at === null && b.last_message_at !== null) return -1;
        if (a.last_message_at !== null && b.last_message_at === null) return 1;
        if (a.last_message_at === null) return 0;
        return b.last_message_at!.localeCompare(a.last_message_at!);
      });
    }
    return Array.from(map.entries());
  }, [sessions, positions, search]);

  return (
    <div className="flex h-full w-full flex-col border-r border-border bg-background">
      <div className="border-b border-border p-3 space-y-2">
        <input
          type="search"
          placeholder="Search threads"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={onAddPosition}
          className="flex w-full items-center gap-2 rounded-md border border-dashed border-border px-2 py-1.5 text-sm hover:bg-muted"
        >
          <Plus className="h-4 w-4" />
          Add position
        </button>
        {isTrialUser && threadsRemaining !== null && (
          <p className="text-xs text-muted-foreground text-center">
            {atThreadCap
              ? "All 3 free dialogs used"
              : `${threadsRemaining} of ${sub!.coach.threads_total} free dialogs left`}
          </p>
        )}
        {atThreadCap && (
          <>
            <p className="text-xs text-muted-foreground text-center opacity-70">
              Deleting a dialog won&apos;t free up a slot.
            </p>
            <button
              type="button"
              onClick={() => checkout.mutate("offer_mode")}
              disabled={checkout.isPending}
              className="w-full rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {checkout.isPending ? "Loading…" : "Upgrade to Offer Mode"}
            </button>
          </>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {groups.length === 0 && (
          <div className="text-center text-sm text-muted-foreground p-4">
            No threads yet. Click &quot;Add position&quot; to start.
          </div>
        )}
        {groups.map(([runId, g]) => {
          const isCollapsed = collapsed.has(runId);
          const label = g.position
            ? `${g.position.job_company ?? ""} — ${g.position.job_title ?? ""}`.trim()
            : "Unknown position";
          return (
            <div key={runId}>
              <div className="flex items-center justify-between px-1 py-1 text-xs font-semibold text-muted-foreground">
                <button
                  type="button"
                  onClick={() => {
                    const next = new Set(collapsed);
                    if (next.has(runId)) next.delete(runId);
                    else next.add(runId);
                    setCollapsed(next);
                  }}
                  className="flex flex-1 items-center gap-1 truncate"
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                  <span className="truncate">{label}</span>
                </button>
                <button
                  type="button"
                  onClick={() => !atThreadCap && onCreateThreadInPosition(runId)}
                  aria-label={atThreadCap ? "Thread limit reached" : "New thread in position"}
                  className={cn(
                    "p-1 rounded",
                    atThreadCap
                      ? "opacity-40 cursor-not-allowed"
                      : "hover:bg-muted",
                  )}
                >
                  {atThreadCap ? (
                    <Lock className="h-3 w-3" />
                  ) : (
                    <Plus className="h-3 w-3" />
                  )}
                </button>
              </div>
              {!isCollapsed && (
                <div className={cn("ml-3 space-y-0.5")}>
                  {g.threads.map((t) => (
                    <ThreadListItem
                      key={t.id}
                      session={t}
                      active={t.id === activeThreadId}
                      onSelect={() => onSelectThread(t.id)}
                      onRename={(title) => onRenameThread(t.id, title)}
                      onDelete={() => onDeleteThread(t.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
