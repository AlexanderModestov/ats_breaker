"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Upload, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CVCard } from "@/components/CVCard";
import { motion, StaggerList, StaggerItem, SlideUp } from "@/components/motion";
import { useCVs, useUploadCV, useDeleteCV } from "@/hooks/useCVs";

export default function CVsPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data: cvs, isLoading: cvsLoading, error: cvsError } = useCVs();
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

  const handleSelectCV = useCallback(
    (cvId: string) => {
      router.push(`/optimize?cv=${cvId}`);
    },
    [router]
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-8"
    >
      {/* Header */}
      <SlideUp className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">My CVs</h1>
          <p className="text-muted-foreground">
            Manage your uploaded resumes
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.tex,.md,.html"
            className="hidden"
            onChange={handleFileSelect}
          />
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="gap-2"
            >
              {uploading ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Uploading...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  Upload Resume
                </>
              )}
            </Button>
          </motion.div>
        </div>
      </SlideUp>

      {/* Content */}
      <SlideUp delay={0.1}>
        {cvsLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2].map((i) => (
              <div key={i} className="h-28 shimmer rounded-xl" />
            ))}
          </div>
        )}

        {cvsError && (
          <Card className="border-destructive/50">
            <CardContent className="pt-6">
              <p className="text-destructive">
                Failed to load resumes: {cvsError.message}
              </p>
            </CardContent>
          </Card>
        )}

        {cvs && cvs.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Upload className="mb-4 h-12 w-12 text-muted-foreground/50" />
              <h3 className="mb-2 font-medium">No resumes uploaded</h3>
              <p className="mb-4 text-center text-sm text-muted-foreground">
                Upload your resume to get started with optimization.
              </p>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                className="gap-2"
              >
                <Upload className="h-4 w-4" />
                Upload Resume
              </Button>
            </CardContent>
          </Card>
        )}

        {cvs && cvs.length > 0 && (
          <StaggerList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cvs.map((cv) => (
              <StaggerItem key={cv.id}>
                <CVCard
                  cv={cv}
                  onSelect={() => handleSelectCV(cv.id)}
                  onDelete={handleDelete}
                />
              </StaggerItem>
            ))}
          </StaggerList>
        )}
      </SlideUp>
    </motion.div>
  );
}
