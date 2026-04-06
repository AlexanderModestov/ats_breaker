"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listStorybank,
  createStorybankEntry,
  updateStorybankEntry,
  deleteStorybankEntry,
} from "@/lib/api";
import type { StorybankEntry, StorybankEntryRequest } from "@/types";

export function useStorybank() {
  return useQuery<StorybankEntry[]>({
    queryKey: ["storybank"],
    queryFn: listStorybank,
    staleTime: 30_000,
  });
}

export function useCreateStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StorybankEntryRequest) => createStorybankEntry(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}

export function useUpdateStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: StorybankEntryRequest }) =>
      updateStorybankEntry(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}

export function useDeleteStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStorybankEntry(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}
