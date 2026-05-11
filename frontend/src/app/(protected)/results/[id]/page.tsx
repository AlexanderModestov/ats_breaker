"use client";

import { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Download, Building2, MapPin, Loader2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResumePreview } from "@/components/ResumePreview";
import { motion, AnimatePresence, SlideUp } from "@/components/motion";
import {
  useOptimizationStatus,
  useDownloadPDF,
  useUpdateOptimizationJob,
} from "@/hooks/useOptimization";
import type { JobParsed, OptimizationStatus } from "@/types";

type EditingField = "title" | "company" | null;

function JobInfoHeader({
  runId,
  status,
  isComplete,
  isFailed,
}: {
  runId: string;
  status: OptimizationStatus;
  isComplete: boolean;
  isFailed: boolean;
}) {
  const [editing, setEditing] = useState<EditingField>(null);
  const [localJob, setLocalJob] = useState<JobParsed | null>(null);
  const update = useUpdateOptimizationJob(runId);
  const job = localJob ?? status.job_parsed;
  const needsReview = new Set(job?.needs_review ?? []);

  const saveField = async (field: "title" | "company", newText: string) => {
    const trimmed = newText.trim();
    if (!trimmed) {
      setEditing(null);
      return;
    }
    try {
      const updated = await update.mutateAsync({ [field]: trimmed });
      setLocalJob(updated.job_parsed);
    } catch (err) {
      console.error("Failed to save job edit:", err);
    } finally {
      setEditing(null);
    }
  };

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
        {!job ? (
          <span className="text-muted-foreground">Optimization in Progress</span>
        ) : editing === "title" ? (
          <InlineEdit
            initial=""
            placeholder="Enter position"
            className="w-full max-w-md bg-transparent border-b border-input px-0 py-0 text-2xl sm:text-3xl font-bold tracking-tight focus:outline-none focus:border-ring"
            onSave={(v) => saveField("title", v)}
            onCancel={() => setEditing(null)}
          />
        ) : needsReview.has("title") ? (
          <button
            type="button"
            onClick={() => setEditing("title")}
            className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <span className="italic">Position not detected — click to set</span>
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : (
          job.title
        )}
      </h1>
      {job && (
        <div className="flex flex-wrap items-center gap-4 text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Building2 className="h-4 w-4" />
            {editing === "company" ? (
              <InlineEdit
                initial=""
                placeholder="Enter company"
                className="w-64 bg-transparent border-b border-input px-0 py-0 text-base focus:outline-none focus:border-ring"
                onSave={(v) => saveField("company", v)}
                onCancel={() => setEditing(null)}
              />
            ) : needsReview.has("company") ? (
              <button
                type="button"
                onClick={() => setEditing("company")}
                className="inline-flex items-center gap-1.5 italic hover:text-foreground"
              >
                Company not detected — click to set
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            ) : (
              <span>{job.company}</span>
            )}
          </div>
          {job.location && (
            <div className="flex items-center gap-1.5">
              <MapPin className="h-4 w-4" />
              <span>{job.location}</span>
            </div>
          )}
        </div>
      )}
      {!isComplete && (
        <p className="text-muted-foreground">
          {isFailed
            ? "Optimization failed"
            : "Please wait while we optimize your resume"}
        </p>
      )}
    </div>
  );
}

function InlineEdit({
  initial,
  placeholder,
  className,
  onSave,
  onCancel,
}: {
  initial: string;
  placeholder?: string;
  className?: string;
  onSave: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  return (
    <input
      ref={ref}
      type="text"
      value={value}
      placeholder={placeholder}
      maxLength={200}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onSave(value);
        } else if (e.key === "Escape") {
          e.preventDefault();
          onCancel();
        }
      }}
      onBlur={onCancel}
      className={className}
    />
  );
}

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
          onClick={() => router.push("/optimize")}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
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
          onClick={() => router.push("/optimize")}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
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
      className="mx-auto max-w-3xl space-y-4"
    >
      {/* Header */}
      <SlideUp className="flex items-center justify-between">
        <motion.div whileHover={{ x: -2 }} whileTap={{ scale: 0.98 }}>
          <Button
            variant="ghost"
            onClick={() => router.push("/optimize")}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back</span>
          </Button>
        </motion.div>

        <AnimatePresence>
          {isComplete && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex items-center gap-2"
            >
              <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                <Link href={`/results/${id}/edit`}>
                  <Button variant="outline" className="gap-2">
                    <Pencil className="h-4 w-4" />
                    Edit Resume
                  </Button>
                </Link>
              </motion.div>
              <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
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
            </motion.div>
          )}
        </AnimatePresence>
      </SlideUp>

      {/* Job info */}
      <SlideUp delay={0.1}>
        <JobInfoHeader
          runId={id}
          status={status}
          isComplete={isComplete}
          isFailed={isFailed}
        />
      </SlideUp>

      {/* Processing indicator */}
      <AnimatePresence>
        {!isComplete && !isFailed && (
          <SlideUp delay={0.2}>
            <Card className="border-border/50 shadow-sm">
              <CardContent className="py-6">
                <div className="flex items-center justify-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <span className="text-sm text-muted-foreground">
                    {status.current_step || "Processing..."}
                  </span>
                </div>
              </CardContent>
            </Card>
          </SlideUp>
        )}
      </AnimatePresence>

      {/* Resume preview */}
      {isComplete && <ResumePreview status={status} />}

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
