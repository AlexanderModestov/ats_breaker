/**
 * Telegram Mini App helpers.
 * Safe to import on web — returns null when not in Telegram.
 */

export function getTelegramWebApp() {
  if (typeof window === "undefined") return null;
  return (window as any).Telegram?.WebApp ?? null;
}

export function getTelegramUserId(): number | null {
  const twa = getTelegramWebApp();
  const id = twa?.initDataUnsafe?.user?.id;
  return typeof id === "number" ? id : null;
}

export function isTelegramMiniApp(): boolean {
  const twa = getTelegramWebApp();
  return !!twa?.platform && twa.platform !== "unknown";
}
