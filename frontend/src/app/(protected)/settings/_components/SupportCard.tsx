"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Check, AlertCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { submitFeedback } from "@/lib/api";

const MAX_LEN = 4000;
const MIN_LEN = 10;

export function SupportCard() {
  const [message, setMessage] = useState("");
  const [justSent, setJustSent] = useState(false);

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
    mutation.mutate({ type: "idea", message: trimmed });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Support / Feedback</CardTitle>
        <CardDescription>
          Tell us anything — bugs, ideas, refunds. We read every message.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="What's on your mind?"
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
