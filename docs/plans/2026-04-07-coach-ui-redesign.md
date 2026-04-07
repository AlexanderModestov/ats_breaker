# Coach UI Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the storybank sidebar with a tab switcher (Chat / Storybank), and add an empty-state hint screen to the chat with a description and clickable suggestion chips.

**Architecture:** The coach page switches from a horizontal flex layout (chat + sidebar) to a single-column layout with a tab bar in the header. `StorybankPanel` is simplified to a full-width scrollable list. `CoachChat` gains an empty-state screen with a description block and suggestion chips that fill the textarea on click.

**Tech Stack:** Next.js 14 (App Router), React, Tailwind CSS, Framer Motion, lucide-react

---

### Task 1: Refactor `coach/page.tsx` — replace sidebar with tabs

**Files:**
- Modify: `frontend/src/app/(protected)/coach/page.tsx`

**Step 1: Replace `storybankCollapsed` state with `activeTab`**

Change:
```tsx
const [storybankCollapsed, setStorybankCollapsed] = useState(false);
```
To:
```tsx
const [activeTab, setActiveTab] = useState<"chat" | "storybank">("chat");
```

**Step 2: Replace the JSX layout**

Remove the entire `<motion.div>` content and replace with this layout:

```tsx
return (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    className="mx-auto flex h-[calc(100vh-4rem)] max-w-7xl flex-col"
  >
    {/* Header: position selector + tabs */}
    <div className="flex items-center justify-between border-b border-border px-4 py-3 gap-4">
      <select
        value={selectedRunId || ""}
        onChange={(e) => handlePositionChange(e.target.value)}
        className="flex-1 max-w-md rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <option value="" disabled>
          Select a position...
        </option>
        {positions.map((p) => (
          <option key={p.id} value={p.id}>
            {p.job_company} — {p.job_title}
          </option>
        ))}
      </select>

      {/* Tab switcher */}
      <div className="flex rounded-lg border border-border bg-muted p-0.5 text-sm shrink-0">
        <button
          className={cn(
            "rounded-md px-4 py-1.5 font-medium transition-colors",
            activeTab === "chat"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setActiveTab("chat")}
        >
          Chat
        </button>
        <button
          className={cn(
            "flex items-center gap-1.5 rounded-md px-4 py-1.5 font-medium transition-colors",
            activeTab === "storybank"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setActiveTab("storybank")}
        >
          Storybank
          {storybankCount > 0 && (
            <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
              {storybankCount}
            </span>
          )}
        </button>
      </div>
    </div>

    {/* Tab content */}
    <div className="flex-1 overflow-hidden">
      {activeTab === "chat" ? (
        selectedRunId ? (
          <CoachChat
            messages={messages}
            isStreaming={isStreaming}
            onSend={handleSend}
            runId={selectedRunId}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <p className="text-sm">Select a position to start coaching</p>
          </div>
        )
      ) : (
        <StorybankPanel />
      )}
    </div>
  </motion.div>
);
```

**Step 3: Add `storybankCount` derived value and `cn` import**

Add after the `positions` derivation:
```tsx
const { data: stories = [] } = useStorybank();
const storybankCount = stories.length;
```

Add `cn` to imports from `@/lib/utils`:
```tsx
import { cn } from "@/lib/utils";
```

**Step 4: Remove the now-unused `refetchStorybank` effect**

The storybank data is always live via React Query — remove:
```tsx
const { refetch: refetchStorybank } = useStorybank();
useEffect(() => {
  if (!isStreaming && sessionId) {
    refetchStorybank();
  }
}, [isStreaming, sessionId, refetchStorybank]);
```

**Step 5: Verify in browser**

- Tab bar appears in header
- Clicking "Storybank" tab shows storybank content full-width
- Clicking "Chat" tab shows chat
- No sidebar visible

**Step 6: Commit**

```bash
git add frontend/src/app/\(protected\)/coach/page.tsx
git commit -m "feat(coach): replace storybank sidebar with tab switcher"
```

---

### Task 2: Simplify `StorybankPanel` to full-width mode

**Files:**
- Modify: `frontend/src/components/StorybankPanel.tsx`

**Step 1: Remove the `StorybankPanelProps` interface and collapsed/sidebar logic**

Replace the entire `StorybankPanel` export with a no-props version:

```tsx
export function StorybankPanel() {
  const { data: stories = [], isLoading } = useStorybank();

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <BookOpen className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold text-foreground">Storybank</h2>
        <Badge variant="secondary" className="text-[10px] font-normal">
          {stories.length}
        </Badge>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <span className="text-sm text-muted-foreground">Loading...</span>
          </div>
        ) : stories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <BookOpen className="mb-3 h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              No stories yet. Chat with the career coach to build your storybank.
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl space-y-2">
            {stories.map((entry) => (
              <StoryCard key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Remove unused imports**

Remove from imports: `X`, `ChevronRight` (if ChevronRight is still used in StoryCard keep it), motion-related sidebar animation imports aren't needed in panel itself. Keep `motion` and `AnimatePresence` for `StoryCard`.

**Step 3: Verify**

- Storybank tab shows a clean full-width list centered at max-w-2xl
- Cards expand/collapse, edit/delete work as before

**Step 4: Commit**

```bash
git add frontend/src/components/StorybankPanel.tsx
git commit -m "feat(coach): simplify StorybankPanel to full-width layout"
```

---

### Task 3: Add empty-state hints to `CoachChat`

**Files:**
- Modify: `frontend/src/components/CoachChat.tsx`

**Step 1: Add `runId` prop and suggestion chips data**

Update the interface:
```tsx
interface CoachChatProps {
  messages: CoachMessage[];
  isStreaming: boolean;
  onSend: (message: string) => void;
  runId: string;
}
```

Add the suggestions array inside the component (before the return):
```tsx
const SUGGESTIONS = [
  "What's most important for this role?",
  "Practice a leadership question with me",
  "Give me feedback on my answer",
  "What questions should I expect?",
];
```

**Step 2: Replace the empty-state JSX**

Replace:
```tsx
{messages.length === 0 ? (
  <div className="flex h-full items-center justify-center">
    <div className="text-center">
      <h3 className="text-lg font-semibold">Interview Coach</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Ask questions about the role, practice answers, or get feedback on your resume.
      </p>
    </div>
  </div>
) : (
```

With:
```tsx
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
          "Save your best stories to Storybank",
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
```

**Step 3: Verify**

- Empty chat shows description + bullet list + 4 suggestion chips
- Clicking a chip fills the textarea (does not auto-send)
- Once messages exist, chips disappear

**Step 4: Commit**

```bash
git add frontend/src/components/CoachChat.tsx
git commit -m "feat(coach): add empty state with description and suggestion chips"
```

---

### Task 4: Final check

**Step 1: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

**Step 2: Manual smoke test**

1. Open `/coach`
2. No position selected → "Select a position" message
3. Select a position → empty chat with hints and chips
4. Click a chip → textarea fills
5. Send a message → chat works
6. Click "Storybank" tab → full-width panel
7. Stories expand/collapse/edit/delete
8. Badge on tab shows story count
