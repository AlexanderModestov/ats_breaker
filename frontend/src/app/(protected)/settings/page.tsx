"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { getProfile, updateProfile } from "@/lib/api";
import type { Theme, UserProfile } from "@/types";

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const { data: profile, isLoading } = useQuery<UserProfile>({
    queryKey: ["profile"],
    queryFn: getProfile,
  });

  const [name, setName] = useState("");
  const [theme, setTheme] = useState<Theme>("minimal");
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (profile) {
      setName(profile.name || "");
      setTheme(profile.theme);
    }
  }, [profile]);

  useEffect(() => {
    if (profile) {
      const nameChanged = name !== (profile.name || "");
      const themeChanged = theme !== profile.theme;
      setHasChanges(nameChanged || themeChanged);
    }
  }, [name, theme, profile]);

  const updateMutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (updated) => {
      queryClient.setQueryData(["profile"], updated);
      setHasChanges(false);
    },
  });

  const handleSave = () => {
    const updates: { name?: string; theme?: Theme } = {};
    if (name !== (profile?.name || "")) {
      updates.name = name;
    }
    if (theme !== profile?.theme) {
      updates.theme = theme;
    }
    if (Object.keys(updates).length > 0) {
      updateMutation.mutate(updates);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="animate-pulse text-muted-foreground">
          Loading settings...
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your personal information</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Email</label>
            <Input value={profile?.email || ""} disabled />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
          <CardDescription>Choose your preferred color scheme</CardDescription>
        </CardHeader>
        <CardContent>
          <ThemeSwitcher value={theme} onChange={setTheme} />
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          disabled={!hasChanges}
          onClick={() => {
            if (profile) {
              setName(profile.name || "");
              setTheme(profile.theme);
            }
          }}
        >
          Cancel
        </Button>
        <Button
          disabled={!hasChanges || updateMutation.isPending}
          onClick={handleSave}
        >
          {updateMutation.isPending ? "Saving..." : "Save Changes"}
        </Button>
      </div>

      {updateMutation.error && (
        <p className="text-center text-sm text-destructive">
          Failed to save: {updateMutation.error.message}
        </p>
      )}
    </div>
  );
}
