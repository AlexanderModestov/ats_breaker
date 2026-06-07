"use client";

import { useMemo } from "react";
import { Lock, Zap } from "lucide-react";
import type { OptimizationSummary } from "@/types";
import { useCoachTrialStatus } from "@/hooks/useCoachTrialStatus";
import { usePricingModal } from "@/context/PricingModalContext";

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
  const { open: openPricing } = usePricingModal();
  const { isPositionLocked } = useCoachTrialStatus();

  const candidates = useMemo(
    () =>
      positions.filter(
        (p) => !existingPositionIds.has(p.id) && p.status === "complete" && p.job_title,
      ),
    [positions, existingPositionIds],
  );

  if (!open) return null;

  const hasLocked = candidates.some((p) => isPositionLocked(p.job_company));

  const handleUpgrade = () => {
    onClose();
    openPricing({ minTier: "offer_mode" });
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        onClick={onClose}
      >
        <div
          className="w-full max-w-md rounded-lg border border-border bg-background shadow-lg overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-4">
            <h3 className="text-sm font-semibold mb-3">Pick a position</h3>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No positions available — finish an optimization first.
              </p>
            ) : (
              <ul className="max-h-64 overflow-y-auto divide-y divide-border">
                {candidates.map((p) => {
                  const locked = isPositionLocked(p.job_company);
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        className={
                          locked
                            ? "w-full px-2 py-2 text-left text-sm rounded flex items-center justify-between gap-2 bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/20 dark:hover:bg-amber-950/30"
                            : "w-full px-2 py-2 text-left text-sm rounded flex items-center justify-between gap-2 hover:bg-muted"
                        }
                        onClick={() => {
                          if (locked) {
                            handleUpgrade();
                          } else {
                            onPick(p.id);
                            onClose();
                          }
                        }}
                      >
                        <span className={locked ? "text-amber-900 dark:text-amber-200" : undefined}>
                          {p.job_company} — {p.job_title}
                        </span>
                        {locked && (
                          <span className="flex items-center gap-1 shrink-0 text-xs font-medium text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 rounded-full">
                            <Lock className="h-3 w-3" />
                            Upgrade
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {hasLocked && (
            <div className="px-4 py-3 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 border-t border-amber-200 dark:border-amber-800 flex items-center justify-between gap-3">
              <p className="text-xs text-amber-800 dark:text-amber-300 leading-snug">
                <span className="font-semibold">Unlock all companies</span> — coach any position, not just one.
              </p>
              <button
                type="button"
                onClick={handleUpgrade}
                className="shrink-0 flex items-center gap-1 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600 px-3 py-1.5 rounded-md transition-colors"
              >
                <Zap className="h-3 w-3" />
                Upgrade
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
