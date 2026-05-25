"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useLinkTelegram } from "@/hooks/useLinkTelegram";
import { useTelegramAutoLogin } from "@/hooks/useTelegramAutoLogin";
import { Sidebar } from "@/components/Sidebar";
import { motion } from "framer-motion";
import { PricingModalProvider } from "@/context/PricingModalContext";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, loading } = useAuth();
  const { attempting } = useTelegramAutoLogin();

  useLinkTelegram();

  useEffect(() => {
    if (!loading && !attempting && !isAuthenticated) {
      router.push("/signin");
    }
  }, [isAuthenticated, loading, attempting, router]);

  if (loading || attempting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="relative">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
          </div>
          <p className="text-sm text-muted-foreground">Loading...</p>
        </motion.div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <PricingModalProvider>
      <div className="flex min-h-screen bg-white">
        <Sidebar />
        <motion.main
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="flex-1 overflow-x-hidden pb-16 lg:pb-0"
        >
          <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
            {children}
          </div>
        </motion.main>
      </div>
    </PricingModalProvider>
  );
}
