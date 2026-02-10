"use client";

import { Download, Eye, CheckCircle, AlertCircle, ChevronDown } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { motion, AnimatePresence } from "@/components/motion";
import { cn } from "@/lib/utils";
import type { OptimizationStatus } from "@/types";

// CSS styles matching the PDF template (resume_wrapper.html)
const resumeStyles = `
  .resume-preview {
    font-family: "Times New Roman", Times, Georgia, serif;
    font-size: 11pt;
    line-height: 1.25;
    color: #000;
    background: white;
    padding: 0.4in;
    max-width: 8.5in;
    margin: 0 auto;
  }
  .resume-preview * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
  .resume-preview a {
    color: #000;
    text-decoration: underline;
  }
  .resume-preview .header {
    text-align: center;
    margin-bottom: 8pt;
  }
  .resume-preview .name {
    font-size: 14pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 2pt;
    margin-bottom: 4pt;
  }
  .resume-preview .contact-line {
    font-size: 10pt;
  }
  .resume-preview .contact-line .sep {
    margin: 0 6pt;
    color: #666;
  }
  .resume-preview .section {
    margin-top: 10pt;
  }
  .resume-preview .section-title {
    font-weight: bold;
    text-transform: uppercase;
    font-size: 11pt;
    letter-spacing: 1pt;
    border-bottom: 1pt solid #000;
    padding-bottom: 2pt;
    margin-bottom: 6pt;
  }
  .resume-preview .section-content {
    padding-left: 0;
  }
  .resume-preview .summary {
    text-align: justify;
    line-height: 1.3;
  }
  .resume-preview .entry {
    margin-bottom: 8pt;
  }
  .resume-preview .entry-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 2pt;
  }
  .resume-preview .entry-main {
    flex: 1;
  }
  .resume-preview .entry-date {
    text-align: right;
    white-space: nowrap;
    margin-left: 8pt;
  }
  .resume-preview .company, .resume-preview .institution {
    font-weight: bold;
  }
  .resume-preview .title, .resume-preview .degree {
    font-style: italic;
  }
  .resume-preview .location {
    color: #444;
  }
  .resume-preview .bullets {
    list-style: none !important;
    margin: 0;
    padding: 0;
  }
  .resume-preview .bullets li {
    position: relative;
    padding-left: 12pt;
    margin-bottom: 1pt;
    text-align: justify;
    line-height: 1.25;
  }
  .resume-preview .bullets li::before {
    content: "•";
    position: absolute;
    left: 0;
    color: #000;
  }
  .resume-preview .skills-list {
    text-align: justify;
    line-height: 1.3;
  }
  .resume-preview .project {
    margin-bottom: 4pt;
  }
  .resume-preview .project-name {
    font-weight: bold;
  }
  .resume-preview .simple-list {
    list-style: none !important;
    margin: 0;
    padding: 0;
  }
  .resume-preview .simple-list li {
    position: relative;
    padding-left: 12pt;
    margin-bottom: 1pt;
  }
  .resume-preview .simple-list li::before {
    content: "•";
    position: absolute;
    left: 0;
  }
`;

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
  const [showFilters, setShowFilters] = useState(false);
  const isComplete = status.status === "complete";
  const hasHtml = !!status.result_html;

  if (!isComplete) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-6"
    >
      {/* Preview Card */}
      <Card className="overflow-hidden border-border/50 shadow-sm">
        <CardHeader className="border-b border-border/50 bg-secondary/30">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg">Preview</CardTitle>
              <CardDescription>
                {status.job_parsed
                  ? `Optimized for ${status.job_parsed.title}`
                  : "Optimized resume"}
              </CardDescription>
            </div>
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button onClick={onDownload} disabled={downloading} className="gap-2">
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
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {hasHtml && (
            <div className="relative">
              <style dangerouslySetInnerHTML={{ __html: resumeStyles }} />
              <div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-full bg-background/80 px-3 py-1.5 text-xs text-muted-foreground backdrop-blur-sm">
                <Eye className="h-3.5 w-3.5" />
                <span>Preview</span>
              </div>
              <div className="overflow-auto bg-gray-100 p-4 pt-12">
                <div
                  className="resume-preview shadow-lg"
                  dangerouslySetInnerHTML={{ __html: status.result_html! }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Filter Results - Collapsible */}
      {status.feedback && status.feedback.length > 0 && (
        <Card className="border-border/50 shadow-sm">
          <CardHeader
            className="cursor-pointer transition-colors hover:bg-secondary/30"
            onClick={() => setShowFilters(!showFilters)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-100">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                </div>
                <div>
                  <CardTitle className="text-base">Quality Checks Passed</CardTitle>
                  <CardDescription>
                    {status.feedback.length} iteration{status.feedback.length > 1 ? "s" : ""} completed
                  </CardDescription>
                </div>
              </div>
              <motion.div
                animate={{ rotate: showFilters ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown className="h-5 w-5 text-muted-foreground" />
              </motion.div>
            </div>
          </CardHeader>

          <AnimatePresence>
            {showFilters && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <CardContent className="border-t border-border/50 pt-6">
                  <div className="space-y-6">
                    {status.feedback.map((iteration, iterationIndex) => (
                      <motion.div
                        key={iteration.iteration}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: iterationIndex * 0.05 }}
                        className="space-y-3"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">
                            Iteration {iteration.iteration}
                          </span>
                          {iteration.passed ? (
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                              Passed
                            </span>
                          ) : (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                              Refined
                            </span>
                          )}
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {iteration.results.map((result) => (
                            <div
                              key={result.filter_name}
                              className={cn(
                                "rounded-lg border p-3 transition-colors",
                                result.passed
                                  ? "border-green-200 bg-green-50/50"
                                  : "border-amber-200 bg-amber-50/50"
                              )}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium">
                                  {result.filter_name}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  {result.passed ? (
                                    <CheckCircle className="h-3.5 w-3.5 text-green-600" />
                                  ) : (
                                    <AlertCircle className="h-3.5 w-3.5 text-amber-600" />
                                  )}
                                  <span className="text-xs text-muted-foreground">
                                    {(result.score * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </div>
                              {result.issues.length > 0 && (
                                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                                  {result.issues.slice(0, 2).map((issue, i) => (
                                    <li key={i} className="line-clamp-1">
                                      {issue}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </CardContent>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      )}
    </motion.div>
  );
}
