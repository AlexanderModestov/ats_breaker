"use client";

import Link from "next/link";
import { motion, ease } from "@/components/motion";
import { Button } from "@/components/ui/button";

export function HeroSection() {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden bg-zinc-950">
      {/* Violet radial bloom */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 65%, rgba(124, 58, 237, 0.15) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-3xl px-4 text-center sm:px-6">
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: ease.smooth }}
          className="text-5xl font-bold tracking-tight text-white sm:text-6xl"
        >
          Transform your resume
          <br />
          for every job posting.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: ease.smooth }}
          className="mt-6 text-lg text-zinc-400"
        >
          AI-powered. ATS-ready. One click.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: ease.smooth }}
          className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center"
        >
          <Link href="/signin">
            <Button className="bg-violet-700 px-8 py-6 text-base font-medium text-white hover:bg-violet-800">
              Get started free
            </Button>
          </Link>
          <a href="#how-it-works">
            <Button
              variant="ghost"
              className="px-8 py-6 text-base text-white/80 hover:bg-white/10 hover:text-white"
            >
              See how it works
            </Button>
          </a>
        </motion.div>
      </div>
    </section>
  );
}
