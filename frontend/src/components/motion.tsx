"use client";

import { motion, AnimatePresence, type Variants } from "framer-motion";
import { type ReactNode } from "react";

// Easing curves
export const ease = {
  smooth: [0.4, 0, 0.2, 1],
  snappy: [0.4, 0, 0, 1],
  bounce: [0.68, -0.55, 0.265, 1.55],
} as const;

// Common animation variants
export const fadeIn: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.4, ease: ease.smooth } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

export const fadeSlideUp: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: ease.smooth }
  },
  exit: {
    opacity: 0,
    y: -10,
    transition: { duration: 0.2 }
  },
};

export const fadeSlideIn: Variants = {
  initial: { opacity: 0, x: -20 },
  animate: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.4, ease: ease.smooth }
  },
  exit: {
    opacity: 0,
    x: 20,
    transition: { duration: 0.2 }
  },
};

export const scaleIn: Variants = {
  initial: { opacity: 0, scale: 0.95 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.3, ease: ease.snappy }
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    transition: { duration: 0.2 }
  },
};

export const staggerContainer: Variants = {
  initial: {},
  animate: {
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
};

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 15 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: ease.smooth }
  },
};

// Stagger wrapper for lists
interface StaggerListProps {
  children: ReactNode;
  className?: string;
  delay?: number;
}

export function StaggerList({ children, className, delay = 0.1 }: StaggerListProps) {
  return (
    <motion.div
      initial="initial"
      animate="animate"
      variants={{
        initial: {},
        animate: {
          transition: {
            staggerChildren: 0.06,
            delayChildren: delay,
          },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Individual stagger item
interface StaggerItemProps {
  children: ReactNode;
  className?: string;
}

export function StaggerItem({ children, className }: StaggerItemProps) {
  return (
    <motion.div
      variants={staggerItem}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Slide up fade wrapper
interface SlideUpProps {
  children: ReactNode;
  className?: string;
  delay?: number;
}

export function SlideUp({ children, className, delay = 0 }: SlideUpProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: ease.smooth }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Presence wrapper for conditional rendering
export { AnimatePresence };
export { motion };
