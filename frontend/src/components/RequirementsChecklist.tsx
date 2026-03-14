"use client";
import { useState } from "react";
import { Check, X, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RequirementItem } from "@/types";

interface Props {
  requirements: RequirementItem[];
  loading: boolean;
  onAddRequirement: (instruction: string) => void;
  isEditing: boolean;
}

export default function RequirementsChecklist({
  requirements,
  loading,
  onAddRequirement,
  isEditing,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [customInstruction, setCustomInstruction] = useState("");

  const covered = requirements.filter((r) => r.covered);
  const uncovered = requirements.filter((r) => !r.covered);

  const handleClick = (req: RequirementItem) => {
    if (req.covered) return;
    const defaultInstruction = `Add to resume: ${req.text}`;
    setEditingId(req.id);
    setCustomInstruction(defaultInstruction);
  };

  const handleSend = () => {
    if (!customInstruction.trim()) return;
    onAddRequirement(customInstruction);
    setEditingId(null);
    setCustomInstruction("");
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-8 bg-muted rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-muted-foreground">
        {covered.length}/{requirements.length} covered
      </div>

      {uncovered.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase text-destructive">
            Missing
          </div>
          {uncovered.map((req) => (
            <div key={req.id}>
              <button
                onClick={() => handleClick(req)}
                disabled={isEditing}
                className="flex items-center gap-2 w-full text-left text-sm p-2 rounded hover:bg-destructive/10 transition-colors disabled:opacity-50"
              >
                <X className="h-4 w-4 text-destructive shrink-0" />
                <span>{req.text}</span>
              </button>
              {editingId === req.id && (
                <div className="flex gap-2 ml-6 mt-1">
                  <Input
                    value={customInstruction}
                    onChange={(e) => setCustomInstruction(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSend()}
                    className="flex-1 text-sm"
                    autoFocus
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={handleSend}
                    disabled={isEditing}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {covered.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase text-green-600">
            Covered
          </div>
          {covered.map((req) => (
            <div
              key={req.id}
              className="flex items-center gap-2 text-sm p-2 text-muted-foreground"
            >
              <Check className="h-4 w-4 text-green-600 shrink-0" />
              <span>{req.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
