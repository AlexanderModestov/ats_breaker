"use client";

import { Briefcase, Clock, CheckCircle, XCircle, Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { OptimizationSummary } from "@/types";

interface OptimizationCardProps {
  optimization: OptimizationSummary;
  onClick: () => void;
}

function getStatusBadge(status: string) {
  switch (status) {
    case "complete":
      return (
        <Badge variant="default" className="bg-green-600 text-white">
          <CheckCircle className="mr-1 h-3 w-3" />
          Complete
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive">
          <XCircle className="mr-1 h-3 w-3" />
          Failed
        </Badge>
      );
    case "pending":
    case "parse_job":
    case "generate":
    case "validate":
    case "refine":
      return (
        <Badge variant="secondary">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          In Progress
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

export function OptimizationCard({
  optimization,
  onClick,
}: OptimizationCardProps) {
  const title = optimization.job_title || "Untitled Job";
  const company = optimization.job_company || "Unknown Company";

  return (
    <Card
      className="cursor-pointer transition-colors hover:bg-muted/50"
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <CardTitle className="text-lg">{title}</CardTitle>
          {getStatusBadge(optimization.status)}
        </div>
        <CardDescription className="flex items-center gap-1">
          <Briefcase className="h-3 w-3" />
          {company}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {new Date(optimization.created_at).toLocaleDateString()}
        </div>
      </CardContent>
    </Card>
  );
}
