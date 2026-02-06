"use client";

import { Building2, Clock, CheckCircle, XCircle, Loader2, ArrowRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { motion } from "@/components/motion";
import type { OptimizationSummary } from "@/types";

interface OptimizationCardProps {
  optimization: OptimizationSummary;
  onClick: () => void;
}

function getStatusConfig(status: string) {
  switch (status) {
    case "complete":
      return {
        label: "Complete",
        icon: CheckCircle,
        className: "bg-green-100 text-green-700 border-green-200",
      };
    case "failed":
      return {
        label: "Failed",
        icon: XCircle,
        className: "bg-red-100 text-red-700 border-red-200",
      };
    case "pending":
    case "parse_job":
    case "generate":
    case "validate":
    case "refine":
      return {
        label: "In Progress",
        icon: Loader2,
        className: "bg-blue-100 text-blue-700 border-blue-200",
        spinning: true,
      };
    default:
      return {
        label: status,
        icon: Clock,
        className: "bg-secondary text-secondary-foreground",
      };
  }
}

export function OptimizationCard({
  optimization,
  onClick,
}: OptimizationCardProps) {
  const title = optimization.job_title || "Untitled Job";
  const company = optimization.job_company || "Unknown Company";
  const statusConfig = getStatusConfig(optimization.status);
  const StatusIcon = statusConfig.icon;

  const formattedDate = new Date(optimization.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

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
            <Badge
              variant="outline"
              className={`shrink-0 gap-1 border ${statusConfig.className}`}
            >
              <StatusIcon
                className={`h-3 w-3 ${statusConfig.spinning ? "animate-spin" : ""}`}
              />
              <span className="text-xs">{statusConfig.label}</span>
            </Badge>
          </div>
          <CardDescription className="flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5" />
            <span className="line-clamp-1">{company}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              {formattedDate}
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground/50 transition-transform group-hover:translate-x-1 group-hover:text-primary" />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
