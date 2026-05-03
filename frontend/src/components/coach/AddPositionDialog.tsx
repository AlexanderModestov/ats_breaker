"use client";

import { useMemo } from "react";
import type { OptimizationSummary } from "@/types";

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
  const candidates = useMemo(
    () =>
      positions.filter(
        (p) => !existingPositionIds.has(p.id) && p.status === "complete" && p.job_title,
      ),
    [positions, existingPositionIds],
  );

  if (!open) return null;

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
            {candidates.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className="w-full px-2 py-2 text-left text-sm hover:bg-muted rounded"
                  onClick={() => {
                    onPick(p.id);
                    onClose();
                  }}
                >
                  {p.job_company} — {p.job_title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
