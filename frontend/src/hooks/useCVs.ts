"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteCV, getCV, listCVs, uploadCV } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { CV } from "@/types";

export function useCVs() {
  const { isAuthenticated, loading } = useAuth();

  return useQuery<CV[], Error>({
    queryKey: ["cvs"],
    queryFn: listCVs,
    staleTime: 1000 * 60, // 1 minute
    enabled: isAuthenticated && !loading, // Only fetch when authenticated
  });
}

export function useCV(cvId: string | null) {
  const { isAuthenticated, loading } = useAuth();

  return useQuery<CV, Error>({
    queryKey: ["cv", cvId],
    queryFn: () => getCV(cvId!),
    enabled: !!cvId && isAuthenticated && !loading,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

export function useUploadCV() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, name }: { file: File; name?: string }) =>
      uploadCV(file, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cvs"] });
    },
  });
}

export function useDeleteCV() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cvId: string) => deleteCV(cvId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cvs"] });
    },
  });
}
