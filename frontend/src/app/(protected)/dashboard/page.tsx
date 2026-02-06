"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle,
  FileText,
  History,
  Rocket,
  Upload,
  AlertTriangle,
  Plus,
  ArrowRight,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CVCard } from "@/components/CVCard";
import { CVDropdown } from "@/components/CVDropdown";
import { JobInput } from "@/components/JobInput";
import { OptimizationCard } from "@/components/OptimizationCard";
import { motion, AnimatePresence, StaggerList, StaggerItem, SlideUp } from "@/components/motion";
import { useCVs, useUploadCV, useDeleteCV } from "@/hooks/useCVs";
import { useOptimizations, useStartOptimization } from "@/hooks/useOptimization";
import { useSubscription } from "@/hooks/useSubscription";
import type { CV } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("optimize");

  // Optimize tab state
  const [selectedCV, setSelectedCV] = useState<CV | null>(null);
  const [jobInput, setJobInput] = useState("");

  const { data: cvs, isLoading: cvsLoading, error: cvsError } = useCVs();
  const {
    data: optimizations,
    isLoading: optimizationsLoading,
    error: optimizationsError,
  } = useOptimizations();
  const { data: subscription, isLoading: loadingSubscription } = useSubscription();
  const startOptimization = useStartOptimization();
  const uploadCV = useUploadCV();
  const deleteCV = useDeleteCV();

  // Handle URL params for initial CV selection and success messages
  useEffect(() => {
    const cvId = searchParams.get("cv");
    if (cvId && cvs && !selectedCV) {
      const cv = cvs.find((c) => c.id === cvId);
      if (cv) {
        setSelectedCV(cv);
      }
    }

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
      window.history.replaceState({}, "", "/dashboard");
    }
  }, [searchParams, cvs, selectedCV]);

  // Redirect if blocked
  useEffect(() => {
    if (!loadingSubscription && subscription) {
      const remaining = subscription.remaining_requests;
      if (remaining !== null && remaining <= 0 && !subscription.is_unlimited) {
        const reason = subscription.can_buy_addon
          ? "quota_exhausted"
          : "trial_exhausted";
        router.push(`/blocked?reason=${reason}`);
      }
    }
  }, [subscription, loadingSubscription, router]);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploading(true);
      try {
        await uploadCV.mutateAsync({ file });
      } catch (err) {
        console.error("Upload failed:", err);
      } finally {
        setUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [uploadCV]
  );

  const handleDelete = useCallback(
    async (cvId: string) => {
      if (!confirm("Are you sure you want to delete this CV?")) return;
      try {
        await deleteCV.mutateAsync(cvId);
      } catch (err) {
        console.error("Delete failed:", err);
      }
    },
    [deleteCV]
  );

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
            <Alert className="border-green-200 bg-green-50 text-green-800">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <AlertDescription>{successMessage}</AlertDescription>
            </Alert>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <SlideUp className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Optimize your resume for any job posting
        </p>
      </SlideUp>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <SlideUp delay={0.1}>
          <TabsList className="grid w-full max-w-md grid-cols-3 p-1">
            <TabsTrigger value="optimize" className="gap-2">
              <Rocket className="h-4 w-4" />
              <span className="hidden sm:inline">Optimize</span>
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <History className="h-4 w-4" />
              <span className="hidden sm:inline">History</span>
            </TabsTrigger>
            <TabsTrigger value="cvs" className="gap-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">CVs</span>
            </TabsTrigger>
          </TabsList>
        </SlideUp>

        {/* Optimize Tab */}
        <TabsContent value="optimize" className="mt-6">
          <AnimatePresence mode="wait">
            <motion.div
              key="optimize"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="mx-auto max-w-2xl space-y-6"
            >
              {/* CV Selection */}
              <Card className="overflow-hidden border-border/50 shadow-sm transition-shadow hover:shadow-md">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg">Select Resume</CardTitle>
                  <CardDescription>Choose which resume to optimize</CardDescription>
                </CardHeader>
                <CardContent>
                  <CVDropdown
                    cvs={cvs || []}
                    selectedCV={selectedCV}
                    onSelect={setSelectedCV}
                    disabled={cvsLoading}
                  />
                  {cvs?.length === 0 && (
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="mt-3 text-sm text-muted-foreground"
                    >
                      No resumes uploaded yet.{" "}
                      <button
                        onClick={() => setActiveTab("cvs")}
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
                      <Alert className="border-amber-200 bg-amber-50 text-amber-800">
                        <AlertTriangle className="h-4 w-4 text-amber-600" />
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
            </motion.div>
          </AnimatePresence>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="mt-6">
          <AnimatePresence mode="wait">
            <motion.div
              key="history"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="space-y-4"
            >
              {optimizationsLoading && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-32 shimmer rounded-xl" />
                  ))}
                </div>
              )}

              {optimizationsError && (
                <Card className="border-destructive/50">
                  <CardContent className="pt-6">
                    <p className="text-destructive">
                      Failed to load history: {optimizationsError.message}
                    </p>
                  </CardContent>
                </Card>
              )}

              {optimizations && optimizations.length === 0 && (
                <Card className="border-dashed">
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <History className="mb-4 h-12 w-12 text-muted-foreground/50" />
                    <p className="text-center text-muted-foreground">
                      No optimizations yet. Start your first one to see results here.
                    </p>
                  </CardContent>
                </Card>
              )}

              {optimizations && optimizations.length > 0 && (
                <StaggerList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {optimizations.map((opt) => (
                    <StaggerItem key={opt.id}>
                      <OptimizationCard
                        optimization={opt}
                        onClick={() => router.push(`/results/${opt.id}`)}
                      />
                    </StaggerItem>
                  ))}
                </StaggerList>
              )}
            </motion.div>
          </AnimatePresence>
        </TabsContent>

        {/* CVs Tab */}
        <TabsContent value="cvs" className="mt-6">
          <AnimatePresence mode="wait">
            <motion.div
              key="cvs"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="space-y-4"
            >
              <div className="flex justify-end">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.tex,.md,.html"
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Button
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="gap-2"
                  >
                    {uploading ? (
                      <>
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        Uploading...
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4" />
                        Upload Resume
                      </>
                    )}
                  </Button>
                </motion.div>
              </div>

              {cvsLoading && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2].map((i) => (
                    <div key={i} className="h-28 shimmer rounded-xl" />
                  ))}
                </div>
              )}

              {cvsError && (
                <Card className="border-destructive/50">
                  <CardContent className="pt-6">
                    <p className="text-destructive">
                      Failed to load resumes: {cvsError.message}
                    </p>
                  </CardContent>
                </Card>
              )}

              {cvs && cvs.length === 0 && (
                <Card className="border-dashed">
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <Upload className="mb-4 h-12 w-12 text-muted-foreground/50" />
                    <h3 className="mb-2 font-medium">No resumes uploaded</h3>
                    <p className="mb-4 text-center text-sm text-muted-foreground">
                      Upload your resume to get started with optimization.
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => fileInputRef.current?.click()}
                      className="gap-2"
                    >
                      <Upload className="h-4 w-4" />
                      Upload Resume
                    </Button>
                  </CardContent>
                </Card>
              )}

              {cvs && cvs.length > 0 && (
                <StaggerList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {cvs.map((cv) => (
                    <StaggerItem key={cv.id}>
                      <CVCard
                        cv={cv}
                        onSelect={() => {
                          setSelectedCV(cv);
                          setActiveTab("optimize");
                        }}
                        onDelete={handleDelete}
                      />
                    </StaggerItem>
                  ))}
                </StaggerList>
              )}
            </motion.div>
          </AnimatePresence>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
