"use client";

import { useCallback, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Rocket } from "lucide-react";
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
import type { CV } from "@/types";

function OptimizeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCvId = searchParams.get("cv");

  const { data: cvs, isLoading: loadingCVs } = useCVs();
  const startOptimization = useStartOptimization();

  const [selectedCV, setSelectedCV] = useState<CV | null>(null);
  const [jobInput, setJobInput] = useState("");

  // Set initial CV from URL param
  if (initialCvId && cvs && !selectedCV) {
    const cv = cvs.find((c) => c.id === initialCvId);
    if (cv) {
      setSelectedCV(cv);
    }
  }

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
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Optimize Resume</h1>
        <p className="text-muted-foreground">
          Select a CV and provide a job posting to generate an optimized resume
        </p>
      </div>

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
            disabled={loadingCVs}
          />
          {cvs?.length === 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              No CVs uploaded yet.{" "}
              <Button
                variant="link"
                className="h-auto p-0"
                onClick={() => router.push("/dashboard")}
              >
                Upload one first
              </Button>
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
  );
}

export default function OptimizePage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <OptimizeContent />
    </Suspense>
  );
}
