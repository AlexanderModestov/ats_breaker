"use client";

import { useState, useRef, useEffect, useCallback, type KeyboardEvent, type ChangeEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { cn, isMobileDevice, isVoiceRecordingSupported } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { VoiceButton } from "@/components/VoiceButton";
import { transcribeAudio, ApiError } from "@/lib/api";
import type { RecorderError } from "@/hooks/useVoiceRecorder";
import { useAnalytics } from "@/hooks/useAnalytics";
import type { CoachMessage } from "@/types";

const MARKDOWN_COMPONENTS = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }: { children?: React.ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-1 mt-2 font-semibold first:mt-0">{children}</h3>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-1 mt-2 font-semibold first:mt-0">{children}</h3>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-1 mt-2 font-semibold first:mt-0">{children}</h3>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="rounded bg-foreground/10 px-1 py-0.5 font-mono text-xs">
      {children}
    </code>
  ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="my-2 overflow-x-auto rounded bg-foreground/10 p-2 font-mono text-xs">
      {children}
    </pre>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="underline underline-offset-2"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="my-2 border-l-2 border-current/30 pl-3 italic">
      {children}
    </blockquote>
  ),
};

interface CoachChatProps {
  messages: CoachMessage[];
  isStreaming: boolean;
  onSend: (message: string) => void;
}

const SUGGESTIONS = [
  "What's most important for this role?",
  "Practice a leadership question with me",
  "Give me feedback on my answer",
  "What questions should I expect?",
];

const VOICE_ERROR_COPY: Record<RecorderError, string> = {
  permission_denied: "Microphone access denied. Enable it in your browser settings.",
  no_microphone: "Microphone unavailable.",
  unsupported: "Voice recording isn't supported in this browser.",
  too_short: "Hold to record.",
  max_duration: "Max 60 seconds reached.",
  unknown: "Couldn't start recording.",
};

function MessageBubble({ message }: { message: CoachMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[80%] break-words rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "whitespace-pre-wrap bg-primary text-primary-foreground"
            : "bg-secondary text-secondary-foreground"
        )}
      >
        {isUser ? (
          message.content
        ) : (
          <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
            {message.content}
          </Markdown>
        )}
      </div>
    </motion.div>
  );
}

export function CoachChat({ messages, isStreaming, onSend }: CoachChatProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { track } = useAnalytics();

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const [voiceSupported, setVoiceSupported] = useState(false);
  useEffect(() => {
    setVoiceSupported(isMobileDevice() && isVoiceRecordingSupported());
  }, []);

  const [voiceError, setVoiceError] = useState<string | null>(null);

  const handleVoiceCaptured = useCallback(
    async (blob: Blob) => {
      setVoiceError(null);
      try {
        const text = await transcribeAudio(blob);
        const trimmed = text.trim();
        if (!trimmed) {
          setVoiceError("Didn't catch that.");
          return;
        }
        if (isStreaming) {
          setVoiceError("Wait until I finish responding.");
          return;
        }
        onSend(trimmed);
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 413) {
            track("coach_voice_error", { error_type: "transcription_failed" });
            setVoiceError("Recording too long.");
          } else if (e.status === 422) {
            track("coach_voice_error", { error_type: "transcription_failed" });
            setVoiceError("Didn't catch that.");
          } else if (e.status === 429) {
            track("coach_voice_error", { error_type: "rate_limited" });
            setVoiceError("Too many voice messages. Wait a bit.");
          } else {
            track("coach_voice_error", { error_type: "transcription_failed" });
            setVoiceError("Couldn't transcribe. Try again.");
          }
        } else {
          track("coach_voice_error", { error_type: "transcription_failed" });
          setVoiceError("Couldn't transcribe. Try again.");
        }
      }
    },
    [onSend, isStreaming, track],
  );

  const handleResize = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    if (voiceError) setVoiceError(null);
    const textarea = e.target;
    setInput(textarea.value);
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  }, [voiceError]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isStreaming, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4">
            <div className="w-full max-w-md text-center">
              <h3 className="text-lg font-semibold">Interview Coach</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                I know this job posting and your resume. I can help you prepare.
              </p>
              <ul className="mt-4 space-y-1 text-sm text-muted-foreground text-left list-none">
                {[
                  "Practice answering interview questions",
                  "Get feedback on your STAR stories",
                  "Understand what the role really needs",
                ].map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="mt-0.5 text-primary">•</span>
                    {item}
                  </li>
                ))}
              </ul>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setInput(s);
                      textareaRef.current?.focus();
                    }}
                    className="rounded-full border border-border bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-muted"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <MessageBubble key={msg.role + "-" + i} message={msg} />
            ))}
          </AnimatePresence>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-border p-4">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleResize}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-input bg-background px-4 py-3 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
          {voiceSupported && !input.trim() ? (
            <VoiceButton
              disabled={isStreaming}
              onCaptured={handleVoiceCaptured}
              onError={(kind) => {
                track("coach_voice_error", { error_type: kind });
                setVoiceError(VOICE_ERROR_COPY[kind]);
              }}
              onRecordingStart={() => track("coach_voice_recording_started")}
              onRecordingEnd={({ durationMs, cancelled }) =>
                track("coach_voice_recording_completed", { duration_ms: durationMs, cancelled })
              }
            />
          ) : (
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
        {voiceError && (
          <Alert variant="destructive" className="mt-2 py-2 text-xs">
            <AlertDescription>{voiceError}</AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
}
