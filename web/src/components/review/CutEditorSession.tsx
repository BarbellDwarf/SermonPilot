import type { ReactNode } from "react";
import { useCutEditor, type CutEditor, type CutEditorOptions } from "./useCutEditor";

export function CutEditorSession({
  options,
  children,
}: {
  options: CutEditorOptions;
  children: (editor: CutEditor) => ReactNode;
}) {
  const editor = useCutEditor(options);
  return children(editor);
}
