"use client";
import { use, useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Undo2, Redo2, Download, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useResumeEditor } from "@/hooks/useResumeEditor";
import { useOptimizationStatus } from "@/hooks/useOptimization";
import RequirementsChecklist from "@/components/RequirementsChecklist";
import EditPopup from "@/components/EditPopup";
import { downloadPdfFromHtml } from "@/lib/api";

// Script injected into iframe to detect double-clicks on editable elements
const IFRAME_SCRIPT = `
<script>
(function() {
  const EDITABLE = 'p, li, h1, h2, h3, h4, h5, h6, span.title, span.company, span.institution, span.degree, span.project-name, div.summary';
  const NON_EDITABLE = 'h2.section-title, div.contact-line, div.contact-line *';

  function getSelector(el) {
    if (el.id) return '#' + el.id;
    const parts = [];
    let current = el;
    while (current && current !== document.body) {
      let selector = current.tagName.toLowerCase();
      if (current.id) {
        parts.unshift('#' + current.id);
        break;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
        if (siblings.length > 1) {
          const index = siblings.indexOf(current);
          selector += ':nth-of-type(' + (index + 1) + ')';
        }
      }
      parts.unshift(selector);
      current = current.parentElement;
    }
    return parts.join(' > ');
  }

  document.addEventListener('dblclick', function(e) {
    const el = e.target.closest(EDITABLE);
    if (!el) return;
    if (el.closest(NON_EDITABLE) || e.target.closest(NON_EDITABLE)) return;

    const rect = el.getBoundingClientRect();
    window.parent.postMessage({
      type: 'resume-dblclick',
      text: el.textContent || '',
      selector: getSelector(el),
      rect: { top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right }
    }, '*');
  });
})();
</script>`;

export default function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { status } = useOptimizationStatus(id);
  const [downloading, setDownloading] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [editPopup, setEditPopup] = useState<{
    text: string;
    selector: string;
    position: { top: number; left: number };
  } | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const {
    html,
    applyTextEdit,
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

  // Listen for double-click messages from iframe
  const handleMessage = useCallback(
    (e: MessageEvent) => {
      if (e.data?.type !== "resume-dblclick") return;
      const { text, selector, rect } = e.data;
      const iframe = iframeRef.current;
      if (!iframe) return;

      const iframeRect = iframe.getBoundingClientRect();
      setEditPopup({
        text,
        selector,
        position: {
          top: iframeRect.top + rect.bottom + 4,
          left: iframeRect.left + rect.left,
        },
      });
    },
    []
  );

  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [handleMessage]);

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

  const handlePopupSave = (newText: string) => {
    if (editPopup) {
      applyTextEdit(editPopup.selector, newText);
      setEditPopup(null);
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
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
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

      {/* Center — Preview */}
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
            size="sm"
            onClick={handleDownload}
            disabled={downloading}
            className="gap-1"
          >
            <Download className="h-4 w-4" />
            {downloading ? "..." : "PDF"}
          </Button>
        </div>

        {/* Preview */}
        <div className="flex-1 overflow-auto relative">
          <div className="max-w-[8.5in] mx-auto bg-white shadow-md my-4">
            <iframe
              ref={iframeRef}
              srcDoc={`<!DOCTYPE html><html><head><style>body{font-family:'Times New Roman',serif;font-size:11pt;margin:0.4in;line-height:1.25;}[data-editable]:hover{outline:2px dashed hsl(215 20% 65% / 0.5);outline-offset:2px;cursor:text;}</style></head><body>${html}${IFRAME_SCRIPT}</body></html>`}
              className="w-full h-[11in] border-0"
              title="Resume preview"
            />
          </div>
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

      {/* Edit popup */}
      {editPopup && (
        <EditPopup
          text={editPopup.text}
          position={editPopup.position}
          onSave={handlePopupSave}
          onCancel={() => setEditPopup(null)}
        />
      )}
    </div>
  );
}
