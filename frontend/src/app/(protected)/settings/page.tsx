"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
// import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import {
  createBillingPortal,
  getProfile,
  getSubscriptionStatus,
} from "@/lib/api";
import { TIER_LABEL } from "@/lib/tiers";
import type { SubscriptionStatus, UserProfile } from "@/types";
import { SupportCard } from "./_components/SupportCard";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "long" }).format(
    new Date(iso),
  );
}

function SubscriptionCard() {
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery<SubscriptionStatus>({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
  });

  // Refresh on mount in case user just returned from Stripe Billing Portal.
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["subscription"] });
  }, [queryClient]);

  const portalMutation = useMutation({
    mutationFn: () => createBillingPortal(window.location.href),
    onSuccess: ({ checkout_url }) => {
      window.location.href = checkout_url;
    },
  });

  const header = (
    <CardHeader>
      <CardTitle>Subscription</CardTitle>
      <CardDescription>Manage your plan and billing</CardDescription>
    </CardHeader>
  );

  if (isLoading) {
    return (
      <Card>
        {header}
        <CardContent>
          <div className="h-24 animate-pulse rounded-md bg-muted" />
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        {header}
        <CardContent className="space-y-3">
          <p className="text-sm text-destructive">Couldn&apos;t load subscription</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { tier, status, current_period_end } = data;
  const isFree = tier === "free";
  const isActive = !isFree && status === "active";
  const isCancelled = !isFree && status === "cancelled";

  const handlePortal = () => portalMutation.mutate();
  const portalPending = portalMutation.isPending;

  return (
    <Card>
      {header}
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-base font-medium">{TIER_LABEL[tier]}</span>
          {isFree && <Badge variant="secondary">Free</Badge>}
          {isActive && <Badge variant="default">Active</Badge>}
          {isCancelled && (
            <Badge className="border-transparent bg-amber-500 text-white hover:bg-amber-500/80">
              Cancelled
            </Badge>
          )}
        </div>

        {isActive && current_period_end && (
          <p className="text-sm text-muted-foreground">
            Renews on {formatDate(current_period_end)}
          </p>
        )}
        {isCancelled && current_period_end && (
          <p className="text-sm text-muted-foreground">
            Access until {formatDate(current_period_end)}
          </p>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          {isFree && (
            <Link
              href="/pricing"
              className={cn(buttonVariants(), "w-full sm:w-auto")}
            >
              Upgrade
            </Link>
          )}

          {isActive && (
            <>
              <Button
                onClick={handlePortal}
                disabled={portalPending}
                className="w-full sm:w-auto"
              >
                {portalPending ? "Opening..." : "Manage subscription"}
              </Button>
              <Button
                variant="outline"
                onClick={handlePortal}
                disabled={portalPending}
                className="w-full text-destructive hover:text-destructive sm:w-auto"
              >
                Cancel subscription
              </Button>
            </>
          )}

          {isCancelled && (
            <>
              <Button
                onClick={handlePortal}
                disabled={portalPending}
                className="w-full sm:w-auto"
              >
                {portalPending ? "Opening..." : "Resubscribe"}
              </Button>
              <Button
                variant="outline"
                onClick={handlePortal}
                disabled={portalPending}
                className="w-full sm:w-auto"
              >
                Manage subscription
              </Button>
            </>
          )}
        </div>

        {portalMutation.error && (
          <p className="text-sm text-destructive">
            Couldn&apos;t open billing portal
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: profile, isLoading } = useQuery<UserProfile>({
    queryKey: ["profile"],
    queryFn: getProfile,
  });

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

      <p className="text-sm text-muted-foreground">
        Signed in as <span className="font-medium text-foreground">{profile?.email}</span>
      </p>

      <SubscriptionCard />

      <SupportCard />

      {/* TODO: re-enable when theme switching is implemented
      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
          <CardDescription>Choose your preferred color scheme</CardDescription>
        </CardHeader>
        <CardContent>
          <ThemeSwitcher value={theme} onChange={setTheme} />
        </CardContent>
      </Card>
      */}
    </div>
  );
}
