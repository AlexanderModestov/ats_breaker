"use client";
import { use, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Undo2, Redo2, Download, Eye, Code, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useResumeEditor } from "@/hooks/useResumeEditor";
import { useOptimizationStatus } from "@/hooks/useOptimization";
import RequirementsChecklist from "@/components/RequirementsChecklist";
import { downloadPdfFromHtml } from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
});

export default function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { status } = useOptimizationStatus(id);
  const [mode, setMode] = useState<"preview" | "code">("preview");
  const [downloading, setDownloading] = useState(false);
  const [instruction, setInstruction] = useState("");

  const {
    html,
    updateHtml,
    requirements,
    requirementsLoading,
    validationResults,
    sendInstruction,
    isEditing,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useResumeEditor(id, status?.result_html ?? "");

  const handleSendInstruction = () => {
    if (!instruction.trim()) return;
    sendInstruction(instruction);
    setInstruction("");
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await downloadPdfFromHtml(id, html);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "resume.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  if (!status?.result_html) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading editor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Left panel — Requirements */}
      <div className="w-72 border-r overflow-y-auto p-4 flex flex-col gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push(`/results/${id}`)}
          className="gap-2 justify-start"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to results
        </Button>

        <h2 className="font-semibold">Requirements</h2>
        <RequirementsChecklist
          requirements={requirements}
          loading={requirementsLoading}
          onAddRequirement={sendInstruction}
          isEditing={isEditing}
        />

        {/* Validation scores */}
        {validationResults.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Scores</h3>
            {validationResults.map((r) => (
              <div key={r.filter_name} className="flex justify-between text-sm">
                <span>{r.filter_name}</span>
                <span
                  className={r.passed ? "text-green-600" : "text-amber-600"}
                >
                  {(r.score * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Center — Preview/Editor */}
      <div className="flex-1 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-2 border-b p-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={undo}
            disabled={!canUndo}
          >
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={redo}
            disabled={!canRedo}
          >
            <Redo2 className="h-4 w-4" />
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setMode(mode === "preview" ? "code" : "preview")}
            className="gap-1"
          >
            {mode === "preview" ? (
              <Code className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
            {mode === "preview" ? "Code" : "Preview"}
          </Button>
          <Button
            size="sm"
            onClick={handleDownload}
            disabled={downloading}
            className="gap-1"
          >
            <Download className="h-4 w-4" />
            {downloading ? "..." : "PDF"}
          </Button>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-auto">
          {mode === "preview" ? (
            <div className="max-w-[8.5in] mx-auto bg-white shadow-md my-4">
              <iframe
                srcDoc={`<!DOCTYPE html><html><head><style>body{font-family:'Times New Roman',serif;font-size:11pt;margin:0.4in;line-height:1.25;}</style></head><body>${html}</body></html>`}
                className="w-full h-[11in] border-0"
                title="Resume preview"
              />
            </div>
          ) : (
            <MonacoEditor
              height="100%"
              language="html"
              value={html}
              onChange={(value) => value !== undefined && updateHtml(value)}
              options={{
                minimap: { enabled: false },
                wordWrap: "on",
                fontSize: 13,
              }}
            />
          )}
        </div>

        {/* Bottom — Instruction bar */}
        <div className="border-t p-3 flex gap-2">
          <Input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendInstruction()}
            placeholder="Tell AI what to change... (e.g. 'add more about leadership')"
            disabled={isEditing}
          />
          <Button
            onClick={handleSendInstruction}
            disabled={isEditing || !instruction.trim()}
          >
            {isEditing ? "Applying..." : "Apply"}
          </Button>
        </div>
      </div>
    </div>
  );
}
