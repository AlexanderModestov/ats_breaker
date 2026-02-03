"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle,
  FileText,
  History,
  Plus,
  Rocket,
  Upload,
  AlertTriangle,
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
    <div className="space-y-6">
      {successMessage && (
        <Alert className="mb-4 border-green-500/50 text-green-700 dark:text-green-400">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      )}

      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">
          Optimize your resume for job postings
        </p>
      </div>

      <Tabs defaultValue="optimize" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="optimize">
            <Rocket className="mr-2 h-4 w-4" />
            Optimize
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="mr-2 h-4 w-4" />
            History
          </TabsTrigger>
          <TabsTrigger value="cvs">
            <FileText className="mr-2 h-4 w-4" />
            CVs
          </TabsTrigger>
        </TabsList>

        {/* Optimize Tab */}
        <TabsContent value="optimize">
          <div className="mx-auto max-w-2xl space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Select CV</CardTitle>
                <CardDescription>Choose which CV to optimize</CardDescription>
              </CardHeader>
              <CardContent>
                <CVDropdown
                  cvs={cvs || []}
                  selectedCV={selectedCV}
                  onSelect={setSelectedCV}
                  disabled={cvsLoading}
                />
                {cvs?.length === 0 && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No CVs uploaded yet. Go to the CVs tab to upload one.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Job Posting</CardTitle>
                <CardDescription>
                  Provide the job posting URL or paste the text
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

            {subscription &&
              !subscription.is_unlimited &&
              subscription.remaining_requests !== null &&
              subscription.remaining_requests <= 3 &&
              subscription.remaining_requests > 0 && (
                <Alert variant="warning">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    You have {subscription.remaining_requests} request
                    {subscription.remaining_requests === 1 ? "" : "s"} left
                    {subscription.is_trial ? " in your trial" : " this month"}.
                  </AlertDescription>
                </Alert>
              )}

            <Button
              size="lg"
              className="w-full"
              disabled={!canOptimize || startOptimization.isPending}
              onClick={handleOptimize}
            >
              <Rocket className="mr-2 h-4 w-4" />
              {startOptimization.isPending ? "Starting..." : "Start Optimization"}
            </Button>

            {startOptimization.error && (
              <p className="text-center text-sm text-destructive">
                {startOptimization.error.message}
              </p>
            )}
          </div>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          <div className="space-y-4">
            {optimizationsLoading && (
              <div className="text-center text-muted-foreground">
                Loading optimizations...
              </div>
            )}

            {optimizationsError && (
              <Card className="border-destructive">
                <CardContent className="pt-6">
                  <p className="text-destructive">
                    Failed to load optimizations: {optimizationsError.message}
                  </p>
                </CardContent>
              </Card>
            )}

            {optimizations && optimizations.length === 0 && (
              <Card>
                <CardContent className="pt-6">
                  <p className="text-muted-foreground">
                    No optimizations yet. Start your first optimization to see
                    results here.
                  </p>
                </CardContent>
              </Card>
            )}

            {optimizations && optimizations.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {optimizations.map((opt) => (
                  <OptimizationCard
                    key={opt.id}
                    optimization={opt}
                    onClick={() => router.push(`/results/${opt.id}`)}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {/* CVs Tab */}
        <TabsContent value="cvs">
          <div className="space-y-4">
            <div className="flex justify-end">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.tex,.md,.html"
                className="hidden"
                onChange={handleFileSelect}
              />
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                <Upload className="mr-2 h-4 w-4" />
                {uploading ? "Uploading..." : "Upload CV"}
              </Button>
            </div>

            {cvsLoading && (
              <div className="text-center text-muted-foreground">
                Loading CVs...
              </div>
            )}

            {cvsError && (
              <Card className="border-destructive">
                <CardContent className="pt-6">
                  <p className="text-destructive">
                    Failed to load CVs: {cvsError.message}
                  </p>
                </CardContent>
              </Card>
            )}

            {cvs && cvs.length === 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>No CVs yet</CardTitle>
                  <CardDescription>
                    Upload your first CV to get started with optimization.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="mr-2 h-4 w-4" />
                    Upload CV
                  </Button>
                </CardContent>
              </Card>
            )}

            {cvs && cvs.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {cvs.map((cv) => (
                  <CVCard
                    key={cv.id}
                    cv={cv}
                    onSelect={() => {
                      setSelectedCV(cv);
                      // Switch to optimize tab
                      const tabsTrigger = document.querySelector(
                        '[value="optimize"]'
                      ) as HTMLButtonElement;
                      tabsTrigger?.click();
                    }}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
