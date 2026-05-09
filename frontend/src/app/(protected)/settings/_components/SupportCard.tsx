"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Check, AlertCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { submitFeedback, getSubscriptionStatus } from "@/lib/api";
import type { FeedbackType, SubscriptionStatus } from "@/types";

const PLACEHOLDERS: Record<FeedbackType, string> = {
  refund: "Reason for refund + which payment...",
  bug: "What happened? Steps to reproduce...",
  idea: "What would make HR-Breaker better for you?",
};

const MAX_LEN = 4000;
const MIN_LEN = 10;

function formatPeriodEnd(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "long" }).format(
    new Date(iso),
  );
}

export function SupportCard() {
  const [type, setType] = useState<FeedbackType>("refund");
  const [message, setMessage] = useState("");
  const [justSent, setJustSent] = useState(false);

  const { data: subscription } = useQuery<SubscriptionStatus>({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
  });

  const mutation = useMutation({
    mutationFn: submitFeedback,
    onSuccess: () => {
      setMessage("");
      setJustSent(true);
      setTimeout(() => setJustSent(false), 30_000);
    },
  });

  const trimmed = message.trim();
  const valid = trimmed.length >= MIN_LEN && trimmed.length <= MAX_LEN;
  const disabled = !valid || mutation.isPending || justSent;

  const handleSubmit = () => {
    mutation.mutate({ type, message: trimmed });
  };

  const periodEnd = formatPeriodEnd(subscription?.current_period_end ?? null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Support / Feedback</CardTitle>
        <CardDescription>
          Refund requests, bug reports, and ideas — we read every one.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Tabs
          value={type}
          onValueChange={(v) => setType(v as FeedbackType)}
        >
          <TabsList className="flex w-full">
            <TabsTrigger value="refund" className="flex-1">
              Refund
            </TabsTrigger>
            <TabsTrigger value="bug" className="flex-1">
              Bug
            </TabsTrigger>
            <TabsTrigger value="idea" className="flex-1">
              Idea
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {type === "refund" && subscription && (
          <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            Current plan:{" "}
            <span className="font-medium">{subscription.tier}</span>
            {periodEnd && <> · renews {periodEnd}</>}
          </div>
        )}

        <div className="space-y-1">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={PLACEHOLDERS[type]}
            maxLength={MAX_LEN}
            rows={5}
            className="flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={mutation.isPending || justSent}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{trimmed.length < MIN_LEN ? `Min ${MIN_LEN} chars` : ""}</span>
            <span>
              {message.length}/{MAX_LEN}
            </span>
          </div>
        </div>

        {mutation.isError && (
          <div className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Failed to send:{" "}
              {(mutation.error as Error)?.message ?? "Unknown error"}
            </span>
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          {justSent && (
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <Check className="h-4 w-4 text-green-600" />
              Sent — we&apos;ll reach out via email
            </span>
          )}
          <Button onClick={handleSubmit} disabled={disabled}>
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              "Send"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
