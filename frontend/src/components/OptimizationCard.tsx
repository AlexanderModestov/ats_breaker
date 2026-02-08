"use client";

import { Building2, Clock, ExternalLink, ArrowRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { motion } from "@/components/motion";
import type { OptimizationSummary } from "@/types";

interface OptimizationCardProps {
  optimization: OptimizationSummary;
  onClick: () => void;
}

export function OptimizationCard({
  optimization,
  onClick,
}: OptimizationCardProps) {
  const title = optimization.job_title || "Untitled Job";
  const company = optimization.job_company || "Unknown Company";

  const formattedDate = new Date(optimization.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  // Extract domain from URL for display
  const getDisplayUrl = (url: string | null) => {
    if (!url) return null;
    try {
      const parsed = new URL(url);
      return parsed.hostname.replace("www.", "");
    } catch {
      return url;
    }
  };

  const displayUrl = getDisplayUrl(optimization.job_url);

  return (
    <motion.div
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.2 }}
    >
      <Card
        className="group cursor-pointer transition-all duration-200 hover:shadow-md"
        onClick={onClick}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="line-clamp-1 text-base font-medium">
              {title}
            </CardTitle>
          </div>
          <CardDescription className="flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5" />
            <span className="line-clamp-1">{company}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                {formattedDate}
              </div>
              {displayUrl && (
                <div className="flex items-center gap-1 truncate max-w-[120px]">
                  <ExternalLink className="h-3 w-3 shrink-0" />
                  <span className="truncate">{displayUrl}</span>
                </div>
              )}
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground/50 transition-transform group-hover:translate-x-1 group-hover:text-primary" />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
