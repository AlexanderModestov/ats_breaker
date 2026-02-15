"use client";

import { useCallback, useState, Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Rocket, AlertTriangle, CheckCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CVDropdown } from "@/components/CVDropdown";
import { JobInput } from "@/components/JobInput";
import { useCVs } from "@/hooks/useCVs";
import { useStartOptimization } from "@/hooks/useOptimization";
import { useSubscription } from "@/hooks/useSubscription";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { motion, AnimatePresence, SlideUp } from "@/components/motion";
import type { CV } from "@/types";

const CHECKOUT_TS_KEY = "post_checkout_ts";
const CHECKOUT_GRACE_MS = 60_000; // 60 seconds

function isWithinCheckoutGrace(): boolean {
  try {
    const ts = sessionStorage.getItem(CHECKOUT_TS_KEY);
    if (!ts) return false;
    return Date.now() - parseInt(ts, 10) < CHECKOUT_GRACE_MS;
  } catch {
    return false;
  }
}

function OptimizeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const initialCvId = searchParams.get("cv");

  const { data: cvs, isLoading: loadingCVs } = useCVs();
  const startOptimization = useStartOptimization();
  const { data: subscription, isLoading: loadingSubscription } = useSubscription();

  const [selectedCV, setSelectedCV] = useState<CV | null>(null);
  const [jobInput, setJobInput] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [cvInitialized, setCvInitialized] = useState(false);

  // Survive component re-mounts by persisting post-checkout flag in sessionStorage
  const [postCheckout, setPostCheckout] = useState(() => {
    const hasSuccessParam = !!searchParams.get("success");
    if (hasSuccessParam) {
      try { sessionStorage.setItem(CHECKOUT_TS_KEY, String(Date.now())); } catch {}
      return true;
    }
    return isWithinCheckoutGrace();
  });
  const clearPostCheckout = useCallback(() => {
    try { sessionStorage.removeItem(CHECKOUT_TS_KEY); } catch {}
    setPostCheckout(false);
  }, []);

  // Handle CV selection with localStorage persistence
  const handleCVSelect = useCallback((cv: CV) => {
    setSelectedCV(cv);
    localStorage.setItem("lastSelectedCvId", cv.id);
  }, []);

  // Auto-select CV: URL param > localStorage > first CV
  useEffect(() => {
    if (!cvs || cvs.length === 0 || cvInitialized) return;

    // Priority 1: URL parameter
    if (initialCvId) {
      const cv = cvs.find((c) => c.id === initialCvId);
      if (cv) {
        setSelectedCV(cv);
        localStorage.setItem("lastSelectedCvId", cv.id);
        setCvInitialized(true);
        return;
      }
    }

    // Priority 2: Last used CV from localStorage
    const lastCvId = localStorage.getItem("lastSelectedCvId");
    if (lastCvId) {
      const cv = cvs.find((c) => c.id === lastCvId);
      if (cv) {
        setSelectedCV(cv);
        setCvInitialized(true);
        return;
      }
    }

    // Priority 3: First CV in the list
    setSelectedCV(cvs[0]);
    localStorage.setItem("lastSelectedCvId", cvs[0].id);
    setCvInitialized(true);
  }, [cvs, initialCvId, cvInitialized]);

  // Handle success messages from URL params and invalidate stale subscription cache
  useEffect(() => {
    const success = searchParams.get("success");
    if (success === "subscription") {
      setSuccessMessage(
        "Subscription activated! You now have 50 requests per month."
      );
    } else if (success === "addon") {
      setSuccessMessage(
        "Add-on pack purchased! 10 requests have been added to your account."
      );
    }

    if (success) {
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
      window.history.replaceState({}, "", "/optimize");
    }
  }, [searchParams, queryClient]);

  // Poll subscription after checkout until the Stripe webhook is processed
  useEffect(() => {
    if (!postCheckout) return;
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
    }, 2000);
    const timeout = setTimeout(() => {
      clearInterval(interval);
      clearPostCheckout();
    }, CHECKOUT_GRACE_MS);
    return () => { clearInterval(interval); clearTimeout(timeout); };
  }, [postCheckout, queryClient, clearPostCheckout]);

  // Clear post-checkout state once subscription is confirmed active
  useEffect(() => {
    if (postCheckout && subscription && !loadingSubscription) {
      const remaining = subscription.remaining_requests;
      if (remaining === null || remaining > 0 || subscription.is_unlimited) {
        clearPostCheckout();
      }
    }
  }, [postCheckout, subscription, loadingSubscription, clearPostCheckout]);

  // Check access and redirect if blocked (skip during post-checkout grace period)
  useEffect(() => {
    if (postCheckout) return;
    if (!loadingSubscription && subscription) {
      const remaining = subscription.remaining_requests;
      if (remaining !== null && remaining <= 0 && !subscription.is_unlimited) {
        const reason = subscription.can_buy_addon ? "quota_exhausted" : "trial_exhausted";
        router.push(`/blocked?reason=${reason}`);
      }
    }
  }, [subscription, loadingSubscription, router, postCheckout]);

  const handleOptimize = useCallback(async () => {
    if (!selectedCV || !jobInput.trim()) return;

    try {
      const result = await startOptimization.mutateAsync({
        cv_id: selectedCV.id,
        job_input: jobInput.trim(),
      });
      router.push(`/results/${result.run_id}`);
    } catch (err) {
      console.error("Failed to start optimization:", err);
    }
  }, [selectedCV, jobInput, startOptimization, router]);

  const canOptimize = selectedCV && jobInput.trim().length > 0;

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
      <SlideUp className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Optimize Resume</h1>
        <p className="text-muted-foreground">
          Select a CV and provide a job posting to generate an optimized resume
        </p>
      </SlideUp>

      {/* Form */}
      <SlideUp delay={0.1} className="mx-auto max-w-2xl space-y-6">
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

        {/* Warning */}
        <AnimatePresence>
          {subscription &&
            !subscription.is_unlimited &&
            subscription.remaining_requests !== null &&
            subscription.remaining_requests <= 3 &&
            subscription.remaining_requests > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
              >
                <Alert className="border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                  <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                  <AlertDescription>
                    You have {subscription.remaining_requests} request
                    {subscription.remaining_requests === 1 ? "" : "s"} remaining
                    {subscription.is_trial ? " in your trial" : " this month"}.
                  </AlertDescription>
                </Alert>
              </motion.div>
            )}
        </AnimatePresence>

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
