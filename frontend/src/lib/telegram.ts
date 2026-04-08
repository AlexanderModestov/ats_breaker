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
  if (!twa) return null;
  try {
    const user = JSON.parse(twa.initDataUnsafe?.user ?? "null");
    return user?.id ?? null;
  } catch {
    return null;
  }
}

export function isTelegramMiniApp(): boolean {
  return getTelegramWebApp() !== null;
}
