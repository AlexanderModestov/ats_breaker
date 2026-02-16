"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, CreditCard, ShoppingCart, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useSubscription, useSubscriptionCheckout, useAddonCheckout } from "@/hooks/useSubscription";
import { Suspense } from "react";

function BlockedContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reason = searchParams.get("reason") || "trial_exhausted";

  const { data: subscription } = useSubscription({ refetchInterval: 3000 });
  const subscriptionCheckout = useSubscriptionCheckout();
  const addonCheckout = useAddonCheckout();

  // Redirect back if subscription is actually active (e.g. webhook processed after verify-checkout failed)
  useEffect(() => {
    if (!subscription) return;
    const remaining = subscription.remaining_requests;
    if (remaining === null || remaining > 0 || subscription.is_unlimited) {
      router.replace("/optimize");
    }
  }, [subscription, router]);

  const isQuotaExhausted = reason === "quota_exhausted";

  const handleSubscribe = () => {
    subscriptionCheckout.mutate();
  };

  const handleBuyAddon = () => {
    addonCheckout.mutate();
  };

  const renewalDate = subscription?.renewal_date
    ? new Date(subscription.renewal_date).toLocaleDateString()
    : null;

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-6 w-6 text-destructive" />
          </div>
          <CardTitle>
            {isQuotaExhausted ? "Monthly Quota Exhausted" : "Trial Ended"}
          </CardTitle>
          <CardDescription>
            {isQuotaExhausted
              ? "You've used all 50 requests this month."
              : "You've used your 3 free trial requests."}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {isQuotaExhausted ? (
            <>
              <p className="text-center text-sm text-muted-foreground">
                Your quota resets on {renewalDate || "your next billing date"}.
              </p>
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Need more now?</p>
                    <p className="text-sm text-muted-foreground">
                      +10 requests for €5
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={handleBuyAddon}
                    disabled={addonCheckout.isPending}
                  >
                    <ShoppingCart className="mr-2 h-4 w-4" />
                    {addonCheckout.isPending ? "..." : "Buy"}
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-center text-sm text-muted-foreground">
              Subscribe to continue optimizing your resumes with HR-Breaker Pro.
            </p>
          )}
        </CardContent>

        <CardFooter className="flex flex-col gap-2">
          {!isQuotaExhausted && (
            <Button
              size="lg"
              className="w-full"
              onClick={handleSubscribe}
              disabled={subscriptionCheckout.isPending}
            >
              <CreditCard className="mr-2 h-4 w-4" />
              {subscriptionCheckout.isPending
                ? "Redirecting..."
                : "Subscribe - €20/month"}
            </Button>
          )}
          <Button
            variant="ghost"
            className="w-full"
            onClick={() => router.push("/optimize")}
          >
            Back
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

export default function BlockedPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <BlockedContent />
    </Suspense>
  );
}
