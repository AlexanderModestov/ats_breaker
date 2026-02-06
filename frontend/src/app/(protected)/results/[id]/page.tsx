"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Building2, Briefcase, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProgressStepper } from "@/components/ProgressStepper";
import { ResumePreview } from "@/components/ResumePreview";
import { motion, AnimatePresence, SlideUp } from "@/components/motion";
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
      <div className="flex min-h-[60vh] items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading optimization...</p>
        </motion.div>
      </div>
    );
  }

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-auto max-w-2xl space-y-6"
      >
        <Button
          variant="ghost"
          onClick={() => router.push("/dashboard")}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Button>
        <Card className="border-destructive/50">
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load optimization: {error.message}
            </p>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  if (!status) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-auto max-w-2xl space-y-6"
      >
        <Button
          variant="ghost"
          onClick={() => router.push("/dashboard")}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Button>
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground">Optimization not found</p>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  const isComplete = status.status === "complete";
  const isFailed = status.status === "failed";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="mx-auto max-w-3xl space-y-8"
    >
      {/* Header */}
      <SlideUp className="flex items-center justify-between">
        <motion.div whileHover={{ x: -2 }} whileTap={{ scale: 0.98 }}>
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back to Dashboard</span>
          </Button>
        </motion.div>

        <AnimatePresence>
          {isComplete && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Button
                onClick={() => download(id)}
                disabled={downloading}
                className="gap-2"
              >
                {downloading ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Downloading...
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    Download PDF
                  </>
                )}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </SlideUp>

      {/* Job info */}
      <SlideUp delay={0.1}>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            {status.job_parsed ? (
              status.job_parsed.title
            ) : (
              <span className="text-muted-foreground">Optimization in Progress</span>
            )}
          </h1>
          {status.job_parsed && (
            <div className="flex flex-wrap items-center gap-4 text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Building2 className="h-4 w-4" />
                <span>{status.job_parsed.company}</span>
              </div>
              {status.job_parsed.location && (
                <div className="flex items-center gap-1.5">
                  <MapPin className="h-4 w-4" />
                  <span>{status.job_parsed.location}</span>
                </div>
              )}
            </div>
          )}
          <p className="text-muted-foreground">
            {isComplete
              ? "Your optimized resume is ready for download"
              : isFailed
                ? "Optimization failed"
                : "Please wait while we optimize your resume"}
          </p>
        </div>
      </SlideUp>

      {/* Progress */}
      <SlideUp delay={0.2}>
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <ProgressStepper status={status} />
          </CardContent>
        </Card>
      </SlideUp>

      {/* Resume preview */}
      <AnimatePresence>
        {isComplete && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ delay: 0.3, duration: 0.4 }}
          >
            <ResumePreview
              status={status}
              onDownload={() => download(id)}
              downloading={downloading}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Auto-update notice */}
      <AnimatePresence>
        {!isComplete && !isFailed && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-center gap-2 text-center text-sm text-muted-foreground"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
            This page updates automatically
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
