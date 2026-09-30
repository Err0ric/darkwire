// Expandable rows (wire, Elsewhere, vendor pages, /cves) toggle on a click anywhere in the row,
// its open panel included, except where the click means something else.

/** Whether a click inside an expandable row should toggle it: not on a link, button or form
 * control (they keep their own behavior), and not when the click ends a text selection inside the
 * row, so a summary or a CVE ID can be selected and copied. `root` is the whole row. */
export function shouldToggle(target: EventTarget | null, root: Element | null): boolean {
  if ((target as Element | null)?.closest?.("a, button, input, select, textarea, label, summary")) return false
  const selection = typeof window === "undefined" ? null : window.getSelection()
  if (selection && !selection.isCollapsed && selection.toString().trim() !== "") {
    const inRow = (node: Node | null) => !!node && !!root?.contains(node)
    if (!root || inRow(selection.anchorNode) || inRow(selection.focusNode)) return false
  }
  return true
}
