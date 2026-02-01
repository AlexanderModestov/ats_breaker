"use client";

import { Download, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { OptimizationStatus } from "@/types";

interface ResumePreviewProps {
  status: OptimizationStatus;
  onDownload: () => void;
  downloading?: boolean;
}

export function ResumePreview({
  status,
  onDownload,
  downloading,
}: ResumePreviewProps) {
  const isComplete = status.status === "complete";
  const hasHtml = !!status.result_html;

  if (!isComplete) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Result</CardTitle>
            <CardDescription>
              {status.job_parsed
                ? `${status.job_parsed.title} at ${status.job_parsed.company}`
                : "Optimized resume"}
            </CardDescription>
          </div>
          <Button onClick={onDownload} disabled={downloading}>
            <Download className="mr-2 h-4 w-4" />
            {downloading ? "Downloading..." : "Download PDF"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {hasHtml && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Eye className="h-4 w-4" />
              <span>HTML Preview</span>
            </div>
            <div
              className="prose prose-sm max-w-none rounded-lg border bg-white p-6"
              dangerouslySetInnerHTML={{ __html: status.result_html! }}
            />
          </div>
        )}

        {status.feedback && status.feedback.length > 0 && (
          <div className="mt-6 space-y-4">
            <h4 className="font-medium">Filter Results</h4>
            {status.feedback.map((iteration) => (
              <div key={iteration.iteration} className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  Iteration {iteration.iteration}:{" "}
                  {iteration.passed ? (
                    <span className="text-green-600">Passed</span>
                  ) : (
                    <span className="text-yellow-600">Refining</span>
                  )}
                </p>
                <div className="grid gap-2 text-xs">
                  {iteration.results.map((result) => (
                    <div
                      key={result.filter_name}
                      className={`rounded-md border p-2 ${
                        result.passed
                          ? "border-green-200 bg-green-50"
                          : "border-yellow-200 bg-yellow-50"
                      }`}
                    >
                      <div className="flex justify-between">
                        <span className="font-medium">{result.filter_name}</span>
                        <span>
                          {result.score.toFixed(2)} / {result.threshold.toFixed(2)}
                        </span>
                      </div>
                      {result.issues.length > 0 && (
                        <ul className="mt-1 list-inside list-disc text-muted-foreground">
                          {result.issues.slice(0, 3).map((issue, i) => (
                            <li key={i}>{issue}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
