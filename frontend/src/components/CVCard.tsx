"use client";

import { FileText, Trash2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { motion } from "@/components/motion";
import type { CV } from "@/types";

interface CVCardProps {
  cv: CV;
  onSelect?: (cv: CV) => void;
  onDelete?: (cvId: string) => void;
  selected?: boolean;
}

export function CVCard({ cv, onSelect, onDelete, selected }: CVCardProps) {
  const formattedDate = new Date(cv.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <motion.div
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.2 }}
    >
      <Card
        className={`group cursor-pointer transition-all duration-200 hover:shadow-md ${
          selected
            ? "border-primary bg-primary/5 shadow-md"
            : "hover:border-border"
        }`}
        onClick={() => onSelect?.(cv)}
      >
        <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
              <FileText className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <CardTitle className="text-base font-medium">{cv.name}</CardTitle>
              <CardDescription className="text-xs">
                {cv.original_filename}
              </CardDescription>
            </div>
          </div>
          {onDelete && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(cv.id);
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </motion.div>
          )}
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{formattedDate}</span>
            <ArrowRight className="h-4 w-4 text-muted-foreground/50 transition-transform group-hover:translate-x-1 group-hover:text-primary" />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
