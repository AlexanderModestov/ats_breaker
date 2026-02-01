"use client";

import { ChevronDown, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CV } from "@/types";

interface CVDropdownProps {
  cvs: CV[];
  selectedCV: CV | null;
  onSelect: (cv: CV) => void;
  disabled?: boolean;
}

export function CVDropdown({
  cvs,
  selectedCV,
  onSelect,
  disabled,
}: CVDropdownProps) {
  return (
    <div className="relative">
      <Button
        variant="outline"
        className="w-full justify-between"
        disabled={disabled || cvs.length === 0}
        onClick={(e) => {
          const menu = e.currentTarget.nextElementSibling as HTMLElement;
          menu.classList.toggle("hidden");
        }}
      >
        <span className="flex items-center gap-2">
          <FileText className="h-4 w-4" />
          {selectedCV ? selectedCV.name : "Select a CV"}
        </span>
        <ChevronDown className="h-4 w-4" />
      </Button>
      <div className="absolute z-10 mt-1 hidden w-full rounded-md border bg-background shadow-lg">
        {cvs.map((cv) => (
          <button
            key={cv.id}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
            onClick={() => {
              onSelect(cv);
              const menu = document.querySelector(
                ".absolute.z-10"
              ) as HTMLElement;
              menu?.classList.add("hidden");
            }}
          >
            <FileText className="h-4 w-4 text-muted-foreground" />
            {cv.name}
          </button>
        ))}
      </div>
    </div>
  );
}
