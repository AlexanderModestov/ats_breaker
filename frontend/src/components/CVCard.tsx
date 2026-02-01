"use client";

import { FileText, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CV } from "@/types";

interface CVCardProps {
  cv: CV;
  onSelect?: (cv: CV) => void;
  onDelete?: (cvId: string) => void;
  selected?: boolean;
}

export function CVCard({ cv, onSelect, onDelete, selected }: CVCardProps) {
  const formattedDate = new Date(cv.created_at).toLocaleDateString();

  return (
    <Card
      className={`cursor-pointer transition-colors hover:border-primary ${
        selected ? "border-primary bg-primary/5" : ""
      }`}
      onClick={() => onSelect?.(cv)}
    >
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">{cv.name}</CardTitle>
        </div>
        {onDelete && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(cv.id);
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <CardDescription>
          {cv.original_filename} • {formattedDate}
        </CardDescription>
      </CardContent>
    </Card>
  );
}
