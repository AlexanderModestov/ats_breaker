"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Rocket, CheckCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CVDropdown } from "@/components/CVDropdown";
import { JobInput } from "@/components/JobInput";
import { QuotaBanner } from "@/components/QuotaBanner";
import { useCVs } from "@/hooks/useCVs";
import { useStartOptimization } from "@/hooks/useOptimization";
import { useSubscription } from "@/hooks/useSubscription";
import { useAnalytics } from "@/hooks/useAnalytics";
import { motion, AnimatePresence, SlideUp } from "@/components/motion";
import { ApiError } from "@/lib/api";
import { TIER_LABEL } from "@/lib/tiers";
import { usePricingModal } from "@/context/PricingModalContext";
import type { CV } from "@/types";

function OptimizeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { open } = usePricingModal();
  const initialCvId = searchParams.get("cv");

  const { data: cvs, isLoading: loadingCVs } = useCVs();
  const startOptimization = useStartOptimization();
  const { data: subscription } = useSubscription();
  const { track } = useAnalytics();

  const [selectedCV, setSelectedCV] = useState<CV | null>(null);
  const [jobInput, setJobInput] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [cvInitialized, setCvInitialized] = useState(false);

  // Show post-checkout welcome message and refresh subscription
  useEffect(() => {
    const upgraded = searchParams.get("upgraded");
    if (upgraded === "job_hunter" || upgraded === "offer_mode") {
      setSuccessMessage(
        `Welcome to ${TIER_LABEL[upgraded]}! Your subscription is active.`,
      );
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
      window.history.replaceState({}, "", "/optimize");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // CV select with localStorage persistence
  const handleCVSelect = useCallback((cv: CV) => {
    setSelectedCV(cv);
    localStorage.setItem("lastSelectedCvId", cv.id);
  }, []);

  // Auto-select CV: URL param > localStorage > first CV
  useEffect(() => {
    if (!cvs || cvs.length === 0 || cvInitialized) return;

    if (initialCvId) {
      const cv = cvs.find((c) => c.id === initialCvId);
      if (cv) {
        setSelectedCV(cv);
        localStorage.setItem("lastSelectedCvId", cv.id);
        setCvInitialized(true);
        return;
      }
    }

    const lastCvId = localStorage.getItem("lastSelectedCvId");
    if (lastCvId) {
      const cv = cvs.find((c) => c.id === lastCvId);
      if (cv) {
        setSelectedCV(cv);
        setCvInitialized(true);
        return;
      }
    }

    setSelectedCV(cvs[0]);
    localStorage.setItem("lastSelectedCvId", cvs[0].id);
    setCvInitialized(true);
  }, [cvs, initialCvId, cvInitialized]);

  const handleOptimize = useCallback(async () => {
    if (!selectedCV || !jobInput.trim()) return;

    const trimmed = jobInput.trim();
    const isUrl = /^https?:\/\//i.test(trimmed);
    track("job_provided", { input_type: isUrl ? "url" : "text" });

    try {
      const result = await startOptimization.mutateAsync({
        cv_id: selectedCV.id,
        job_input: trimmed,
      });
      router.push(`/results/${result.run_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        queryClient.invalidateQueries({ queryKey: ["subscription"] });
        open();
        return;
      }
      console.error("Failed to start optimization:", err);
    }
  }, [selectedCV, jobInput, startOptimization, router, track, queryClient, open]);

  const quotaExhausted =
    subscription?.tier === "free" &&
    !subscription.is_unlimited &&
    (subscription.remaining ?? 0) <= 0;

  const canOptimize =
    selectedCV && jobInput.trim().length > 0 && !quotaExhausted;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-8"
    >
      {/* Success message */}
      <AnimatePresence>
        {successMessage && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
          >
            <Alert className="border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
              <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
              <AlertDescription>{successMessage}</AlertDescription>
            </Alert>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <SlideUp className="mx-auto max-w-2xl space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Optimize Resume</h1>
        <p className="text-muted-foreground">
          Select a CV and provide a job posting to generate an optimized resume
        </p>
      </SlideUp>

      {/* Form */}
      <SlideUp delay={0.1} className="mx-auto max-w-2xl space-y-6">
        <QuotaBanner />

        {/* CV Selection */}
        <Card className="border-border/50 shadow-sm transition-shadow hover:shadow-md">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Select Resume</CardTitle>
            <CardDescription>Choose which resume to optimize</CardDescription>
          </CardHeader>
          <CardContent>
            <CVDropdown
              cvs={cvs || []}
              selectedCV={selectedCV}
              onSelect={handleCVSelect}
              disabled={loadingCVs}
            />
            {cvs?.length === 0 && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mt-3 text-sm text-muted-foreground"
              >
                No resumes uploaded yet.{" "}
                <button
                  onClick={() => router.push("/cvs")}
                  className="text-accent underline-offset-4 hover:underline"
                >
                  Upload one
                </button>{" "}
                to get started.
              </motion.p>
            )}
          </CardContent>
        </Card>

        {/* Job Input */}
        <Card className="overflow-hidden border-border/50 shadow-sm transition-shadow hover:shadow-md">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Job Posting</CardTitle>
            <CardDescription>
              Paste the job posting URL or description
            </CardDescription>
          </CardHeader>
          <CardContent>
            <JobInput
              value={jobInput}
              onChange={setJobInput}
              disabled={startOptimization.isPending}
            />
          </CardContent>
        </Card>

        {/* Submit Button */}
        <motion.div
          whileHover={{ scale: canOptimize ? 1.01 : 1 }}
          whileTap={{ scale: canOptimize ? 0.99 : 1 }}
        >
          <Button
            size="lg"
            className="group w-full gap-2 py-6 text-base"
            disabled={!canOptimize || startOptimization.isPending}
            onClick={handleOptimize}
          >
            {startOptimization.isPending ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Starting optimization...
              </>
            ) : (
              <>
                <Rocket className="h-4 w-4" />
                Start Optimization
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </>
            )}
          </Button>
        </motion.div>

        {startOptimization.error && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center text-sm text-destructive"
          >
            {startOptimization.error.message}
          </motion.p>
        )}
      </SlideUp>

      {/* Optimization in-progress toast */}
      <AnimatePresence>
        {startOptimization.isPending && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.3 }}
            className="fixed bottom-6 left-6 z-50 flex items-center gap-3 rounded-lg border border-border/50 bg-background px-4 py-3 shadow-lg"
          >
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="text-sm text-muted-foreground">
              Optimization may take a few minutes…
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function OptimizePage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-12">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <OptimizeContent />
    </Suspense>
  );
}
