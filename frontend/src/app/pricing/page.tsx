"use client";

import { useRouter } from "next/navigation";
import { CreditCard, Check, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { useSubscriptionCheckout } from "@/hooks/useSubscription";

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const subscriptionCheckout = useSubscriptionCheckout();

  const handleSubscribe = () => {
    if (!isAuthenticated) {
      router.push("/login?redirect=/pricing");
      return;
    }
    subscriptionCheckout.mutate();
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        <div className="mx-auto max-w-md text-center">
          <h1 className="text-3xl font-bold">HR-Breaker Pro</h1>
          <p className="mt-2 text-muted-foreground">
            Optimize your resume for any job posting
          </p>
        </div>

        <div className="mx-auto mt-12 max-w-sm">
          <Card className="border-2 border-primary">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">Pro Plan</CardTitle>
              <CardDescription>Everything you need to land your dream job</CardDescription>
              <div className="mt-4">
                <span className="text-4xl font-bold">€20</span>
                <span className="text-muted-foreground">/month</span>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              <ul className="space-y-3">
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>50 resume optimizations per month</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>AI-powered ATS optimization</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Keyword matching & analysis</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Professional PDF output</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Cancel anytime</span>
                </li>
              </ul>
            </CardContent>

            <CardFooter>
              <Button
                size="lg"
                className="w-full"
                onClick={handleSubscribe}
                disabled={subscriptionCheckout.isPending || authLoading}
              >
                <CreditCard className="mr-2 h-4 w-4" />
                {subscriptionCheckout.isPending ? "Redirecting..." : "Subscribe Now"}
              </Button>
            </CardFooter>
          </Card>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Need more? Add-on packs available for €5 (+10 requests)
          </p>
        </div>
      </div>
    </div>
  );
}
