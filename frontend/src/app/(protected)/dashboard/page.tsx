"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CVCard } from "@/components/CVCard";
import { useCVs, useUploadCV, useDeleteCV } from "@/hooks/useCVs";

export default function DashboardPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data: cvs, isLoading, error } = useCVs();
  const uploadCV = useUploadCV();
  const deleteCV = useDeleteCV();

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploading(true);
      try {
        await uploadCV.mutateAsync({ file });
      } catch (err) {
        console.error("Upload failed:", err);
      } finally {
        setUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [uploadCV]
  );

  const handleDelete = useCallback(
    async (cvId: string) => {
      if (!confirm("Are you sure you want to delete this CV?")) return;
      try {
        await deleteCV.mutateAsync(cvId);
      } catch (err) {
        console.error("Delete failed:", err);
      }
    },
    [deleteCV]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Manage your CVs and start optimizing
          </p>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.tex,.md,.html"
            className="hidden"
            onChange={handleFileSelect}
          />
          <Button
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? "Uploading..." : "Upload CV"}
          </Button>
          <Button onClick={() => router.push("/optimize")}>
            <Plus className="mr-2 h-4 w-4" />
            New Optimization
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="text-center text-muted-foreground">Loading CVs...</div>
      )}

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load CVs: {error.message}
            </p>
          </CardContent>
        </Card>
      )}

      {cvs && cvs.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>No CVs yet</CardTitle>
            <CardDescription>
              Upload your first CV to get started with optimization.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="mr-2 h-4 w-4" />
              Upload CV
            </Button>
          </CardContent>
        </Card>
      )}

      {cvs && cvs.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cvs.map((cv) => (
            <CVCard
              key={cv.id}
              cv={cv}
              onSelect={() => router.push(`/optimize?cv=${cv.id}`)}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
