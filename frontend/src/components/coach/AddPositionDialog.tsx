"use client";

import { useMemo } from "react";
import { Lock } from "lucide-react";
import type { OptimizationSummary } from "@/types";
import { useSubscription, useCheckout } from "@/hooks/useSubscription";
import { TIER_LABEL } from "@/lib/tiers";

interface Props {
  open: boolean;
  positions: OptimizationSummary[];
  existingPositionIds: Set<string>;
  onPick: (runId: string) => void;
  onClose: () => void;
}

export function AddPositionDialog({
  open,
  positions,
  existingPositionIds,
  onPick,
  onClose,
}: Props) {
  const { data: sub } = useSubscription();
  const checkout = useCheckout();
  const isTrialUser = sub?.coach != null && !sub.coach.is_unlimited;
  const lockedCompany = sub?.coach?.locked_company ?? null;

  const candidates = useMemo(
    () =>
      positions.filter(
        (p) => !existingPositionIds.has(p.id) && p.status === "complete" && p.job_title,
      ),
    [positions, existingPositionIds],
  );

  if (!open) return null;

  const isPositionLocked = (p: OptimizationSummary) =>
    isTrialUser &&
    !!lockedCompany &&
    (p.job_company ?? "").toLowerCase().trim() !== lockedCompany.toLowerCase().trim();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-background p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold mb-3">Pick a position</h3>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No positions available — finish an optimization first.
          </p>
        ) : (
          <ul className="max-h-80 overflow-y-auto divide-y divide-border">
            {candidates.map((p) => {
              const locked = isPositionLocked(p);
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    className="w-full px-2 py-2 text-left text-sm rounded flex items-center justify-between gap-2 hover:bg-muted"
                    onClick={() => {
                      if (locked) {
                        checkout.mutate("job_hunter");
                      } else {
                        onPick(p.id);
                        onClose();
                      }
                    }}
                  >
                    <span className={locked ? "text-muted-foreground" : undefined}>
                      {p.job_company} — {p.job_title}
                    </span>
                    {locked && (
                      <span className="flex items-center gap-1 shrink-0 text-xs text-muted-foreground">
                        <Lock className="h-3 w-3" />
                        {TIER_LABEL["job_hunter"]}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
