"use client";

import { useSubscription } from "@/hooks/useSubscription";

/**
 * Coach chat-quota state derived from the subscription.
 *
 * Paid tiers get a fixed number of coach chats per period; `atChatCap` reports
 * whether the user has exhausted them.
 */
export function useCoachQuota() {
  const { data: sub } = useSubscription();
  const chatsUsed = sub?.coach.chats_used ?? 0;
  const chatsLimit = sub?.coach.chats_limit ?? 0;
  const chatsRemaining = Math.max(0, chatsLimit - chatsUsed);
  const msgsPerChat = sub?.coach.msgs_per_chat ?? 0;
  return { chatsUsed, chatsLimit, chatsRemaining, msgsPerChat, atChatCap: !!sub && chatsRemaining <= 0 };
}
