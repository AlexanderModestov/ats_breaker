"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ProgressStepper } from "@/components/ProgressStepper";
import { ResumePreview } from "@/components/ResumePreview";
import {
  useOptimizationStatus,
  useDownloadPDF,
} from "@/hooks/useOptimization";

export default function ResultsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const { status, error, loading } = useOptimizationStatus(id);
  const { download, downloading } = useDownloadPDF();

  if (loading && !status) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="animate-pulse text-muted-foreground">
          Loading optimization status...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Dashboard
        </Button>
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load optimization: {error.message}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Dashboard
        </Button>
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground">Optimization not found</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isComplete = status.status === "complete";
  const isFailed = status.status === "failed";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Dashboard
        </Button>
        {isComplete && (
          <Button onClick={() => download(id)} disabled={downloading}>
            {downloading ? "Downloading..." : "Download PDF"}
          </Button>
        )}
      </div>

      <div>
        <h1 className="text-2xl font-bold">
          {status.job_parsed
            ? `${status.job_parsed.title} at ${status.job_parsed.company}`
            : "Optimization in Progress"}
        </h1>
        <p className="text-muted-foreground">
          {isComplete
            ? "Your optimized resume is ready"
            : isFailed
              ? "Optimization failed"
              : "Please wait while we optimize your resume"}
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <ProgressStepper status={status} />
        </CardContent>
      </Card>

      {isComplete && (
        <ResumePreview
          status={status}
          onDownload={() => download(id)}
          downloading={downloading}
        />
      )}

      {!isComplete && !isFailed && (
        <p className="text-center text-sm text-muted-foreground">
          This page will automatically update as the optimization progresses.
        </p>
      )}
    </div>
  );
}
