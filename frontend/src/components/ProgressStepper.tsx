"use client";

import { Check, Loader2, X } from "lucide-react";
import { motion, AnimatePresence } from "@/components/motion";
import { cn } from "@/lib/utils";
import type { OptimizationStatus } from "@/types";

const STEPS = [
  { key: "pending", label: "Starting", description: "Initializing optimization" },
  { key: "parse_job", label: "Parsing", description: "Analyzing job posting" },
  { key: "generate", label: "Generating", description: "Creating optimized resume" },
  { key: "validate", label: "Validating", description: "Running quality checks" },
  { key: "refine", label: "Refining", description: "Improving based on feedback" },
  { key: "complete", label: "Complete", description: "Resume ready" },
] as const;

interface ProgressStepperProps {
  status: OptimizationStatus;
}

export function ProgressStepper({ status }: ProgressStepperProps) {
  const currentStepIndex = STEPS.findIndex((s) => s.key === status.status);
  const isFailed = status.status === "failed";
  const isFullyComplete = status.status === "complete";

  return (
    <div className="space-y-6">
      {/* Steps */}
      <div className="relative">
        {/* Progress line */}
        <div className="absolute left-5 top-5 h-[calc(100%-40px)] w-px bg-border">
          <motion.div
            className="absolute left-0 top-0 w-full bg-primary"
            initial={{ height: 0 }}
            animate={{
              height: isFullyComplete
                ? "100%"
                : `${Math.max(0, (currentStepIndex / (STEPS.length - 1)) * 100)}%`,
            }}
            transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
          />
        </div>

        {/* Step items */}
        <div className="relative space-y-4">
          {STEPS.map((step, index) => {
            // When status is "complete", all steps including the last one are complete
            const isComplete = isFullyComplete ? index <= currentStepIndex : index < currentStepIndex;
            const isCurrent = isFullyComplete ? false : index === currentStepIndex;
            const isPending = index > currentStepIndex;

            return (
              <motion.div
                key={step.key}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05, duration: 0.3 }}
                className="flex items-start gap-4"
              >
                {/* Step indicator */}
                <motion.div
                  className={cn(
                    "relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 bg-background transition-colors duration-300",
                    isComplete && "border-primary bg-primary",
                    isCurrent && !isFailed && "border-primary",
                    isCurrent && isFailed && "border-destructive bg-destructive/10",
                    isPending && "border-muted-foreground/20"
                  )}
                  animate={isCurrent && !isFailed ? { scale: [1, 1.05, 1] } : {}}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                >
                  <AnimatePresence mode="wait">
                    {isComplete && (
                      <motion.div
                        key="check"
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        <Check className="h-5 w-5 text-primary-foreground" />
                      </motion.div>
                    )}
                    {isCurrent && !isFailed && (
                      <motion.div
                        key="loading"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <Loader2 className="h-5 w-5 animate-spin text-primary" />
                      </motion.div>
                    )}
                    {isCurrent && isFailed && (
                      <motion.div
                        key="error"
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                      >
                        <X className="h-5 w-5 text-destructive" />
                      </motion.div>
                    )}
                    {isPending && (
                      <motion.span
                        key="number"
                        className="text-sm font-medium text-muted-foreground/50"
                      >
                        {index + 1}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </motion.div>

                {/* Step content */}
                <div className="flex-1 pt-1.5">
                  <p
                    className={cn(
                      "font-medium transition-colors",
                      isComplete && "text-foreground",
                      isCurrent && !isFailed && "text-primary",
                      isCurrent && isFailed && "text-destructive",
                      isPending && "text-muted-foreground/50"
                    )}
                  >
                    {step.label}
                  </p>
                  <p
                    className={cn(
                      "text-sm transition-colors",
                      isPending ? "text-muted-foreground/30" : "text-muted-foreground"
                    )}
                  >
                    {step.description}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Current step detail */}
      <AnimatePresence mode="wait">
        {status.current_step && (
          <motion.div
            key={status.current_step}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.2 }}
            className="rounded-lg bg-muted/50 px-4 py-3"
          >
            <p className="text-sm text-muted-foreground">{status.current_step}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error message */}
      <AnimatePresence>
        {status.error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-lg bg-destructive/10 px-4 py-3"
          >
            <p className="text-sm text-destructive">{status.error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Iteration counter */}
      <AnimatePresence>
        {status.iterations > 0 && status.status !== "complete" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-center gap-2"
          >
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            <span className="text-xs text-muted-foreground">
              Iteration {status.iterations}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
