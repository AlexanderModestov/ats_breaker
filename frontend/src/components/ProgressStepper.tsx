"use client";

import { Check, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { OptimizationStatus } from "@/types";

const STEPS = [
  { key: "pending", label: "Starting" },
  { key: "parse_job", label: "Parsing Job" },
  { key: "generate", label: "Generating" },
  { key: "validate", label: "Validating" },
  { key: "refine", label: "Refining" },
  { key: "complete", label: "Complete" },
] as const;

interface ProgressStepperProps {
  status: OptimizationStatus;
}

export function ProgressStepper({ status }: ProgressStepperProps) {
  const currentStepIndex = STEPS.findIndex((s) => s.key === status.status);
  const isFailed = status.status === "failed";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        {STEPS.map((step, index) => {
          const isComplete = index < currentStepIndex;
          const isCurrent = index === currentStepIndex;
          const isPending = index > currentStepIndex;

          return (
            <div key={step.key} className="flex flex-col items-center gap-2">
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors",
                  isComplete &&
                    "border-primary bg-primary text-primary-foreground",
                  isCurrent &&
                    !isFailed &&
                    "border-primary bg-primary/10 text-primary",
                  isCurrent && isFailed && "border-destructive bg-destructive/10 text-destructive",
                  isPending && "border-muted-foreground/30 text-muted-foreground"
                )}
              >
                {isComplete && <Check className="h-5 w-5" />}
                {isCurrent && !isFailed && (
                  <Loader2 className="h-5 w-5 animate-spin" />
                )}
                {isCurrent && isFailed && <X className="h-5 w-5" />}
                {isPending && <span className="text-sm">{index + 1}</span>}
              </div>
              <span
                className={cn(
                  "text-xs",
                  isCurrent && !isFailed && "font-medium text-primary",
                  isCurrent && isFailed && "font-medium text-destructive",
                  isPending && "text-muted-foreground"
                )}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {status.current_step && (
        <p className="text-center text-sm text-muted-foreground">
          {status.current_step}
        </p>
      )}

      {status.error && (
        <p className="text-center text-sm text-destructive">{status.error}</p>
      )}

      {status.iterations > 0 && (
        <p className="text-center text-xs text-muted-foreground">
          Iteration {status.iterations}
        </p>
      )}
    </div>
  );
}
