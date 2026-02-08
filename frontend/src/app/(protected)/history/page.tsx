"use client";

import { useRouter } from "next/navigation";
import { History } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { OptimizationCard } from "@/components/OptimizationCard";
import { motion, StaggerList, StaggerItem, SlideUp } from "@/components/motion";
import { useOptimizations } from "@/hooks/useOptimization";

export default function HistoryPage() {
  const router = useRouter();
  const {
    data: optimizations,
    isLoading: optimizationsLoading,
    error: optimizationsError,
  } = useOptimizations();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-8"
    >
      {/* Header */}
      <SlideUp className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">History</h1>
        <p className="text-muted-foreground">
          View your past resume optimizations
        </p>
      </SlideUp>

      {/* Content */}
      <SlideUp delay={0.1}>
        {optimizationsLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 shimmer rounded-xl" />
            ))}
          </div>
        )}

        {optimizationsError && (
          <Card className="border-destructive/50">
            <CardContent className="pt-6">
              <p className="text-destructive">
                Failed to load history: {optimizationsError.message}
              </p>
            </CardContent>
          </Card>
        )}

        {optimizations && optimizations.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-12">
              <History className="mb-4 h-12 w-12 text-muted-foreground/50" />
              <p className="text-center text-muted-foreground">
                No optimizations yet. Start your first one to see results here.
              </p>
            </CardContent>
          </Card>
        )}

        {optimizations && optimizations.length > 0 && (
          <StaggerList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {optimizations.map((opt) => (
              <StaggerItem key={opt.id}>
                <OptimizationCard
                  optimization={opt}
                  onClick={() => router.push(`/results/${opt.id}`)}
                />
              </StaggerItem>
            ))}
          </StaggerList>
        )}
      </SlideUp>
    </motion.div>
  );
}
