"use client";

export default function EditorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Break out of the parent layout's max-w-5xl, px-4, and py-8
  // by using negative margins and removing padding
  return (
    <div className="-mx-4 -my-8 sm:-mx-6 lg:-mx-8">
      {children}
    </div>
  );
}
