"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Settings, LogOut, Sparkles, FileText, MessageCircle, History } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/optimize", label: "Optimize", icon: Sparkles },
  { href: "/cvs", label: "CVs", icon: FileText },
  { href: "/coach", label: "Coach", icon: MessageCircle },
  { href: "/history", label: "History", icon: History },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-zinc-200 bg-white lg:flex">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2 border-b border-zinc-200 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-700">
            <span className="text-sm font-bold text-white">HR</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-zinc-900">Breaker</span>
        </div>

        {/* Nav items */}
        <nav className="flex flex-1 flex-col gap-0.5 p-3">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-zinc-50 text-zinc-900"
                    : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
                )}
              >
                {isActive && (
                  <span className="absolute left-0 top-1.5 h-[calc(100%-12px)] w-0.5 rounded-r-full bg-violet-700" />
                )}
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* User section */}
        <div className="border-t border-zinc-200 p-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-600">
              {user?.email?.[0]?.toUpperCase() ?? "U"}
            </div>
            <span className="flex-1 truncate text-xs text-zinc-500">
              {user?.email?.split("@")[0]}
            </span>
            <Link href="/settings">
              <button className="rounded p-1 text-zinc-400 transition-colors hover:text-zinc-700">
                <Settings className="h-3.5 w-3.5" />
              </button>
            </Link>
            <button
              onClick={() => signOut()}
              className="rounded p-1 text-zinc-400 transition-colors hover:text-zinc-700"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile bottom tab bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 flex border-t border-zinc-200 bg-white lg:hidden">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 py-3 text-[10px] font-medium transition-colors",
                isActive ? "text-violet-700" : "text-zinc-400 hover:text-zinc-600"
              )}
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
