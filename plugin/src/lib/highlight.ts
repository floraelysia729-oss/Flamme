/** Open note in Obsidian and highlight paragraph */
import { App, MarkdownView, Editor } from 'obsidian';

export async function openAndHighlight(
  app: App,
  noteName: string,
  searchText?: string,
): Promise<void> {
  // 1. Open the note using Obsidian's native wikilink resolution
  await app.workspace.openLinkText(noteName, '', false);

  // 2. Get the active markdown view and editor
  const view = app.workspace.getActiveViewOfType(MarkdownView);
  if (!view) return;

  const editor = view.editor;
  const content = editor.getValue();

  // 3. If noteName is an entity name (from wikilink), try to auto-highlight relevant content
  if (!searchText || !searchText.trim()) {
    // No search text, just open the note
    return;
  }

  // Auto-search: use Obsidian's built-in global search to find note content containing entity name
  const searchTerms = [noteName];
  const searchQuery = searchTerms.join(' ');

  // Try to trigger Obsidian's global search
  // This will open a search pane, then user can navigate to the note
  try {
    app.workspace.openSearchText(searchQuery, true);
  } catch {
    // If search API not available, just open the note without search
  // app.workspace.openLinkText(noteName, '', false);
    return;
  }

  // 4. Find and highlight the paragraph with search text
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.toLowerCase().includes(searchText.toLowerCase())) {
      // Set cursor to that line
      editor.setCursor({ line: i, ch: 0 });

      // Select the paragraph (to end of line or find end of paragraph)
      const startCh = line.toLowerCase().indexOf(searchText.toLowerCase());
      const endCh = startCh + searchText.length;
      if (endCh <= line.length) {
        editor.setSelection({ line: i, ch: startCh }, { line: i, ch: endCh });
      } else {
        editor.setSelection({ line: i, ch: startCh }, { line: i, ch: line.length });
      }

      // Scroll into view
      editor.scrollIntoView(
        { from: { line: i, ch: startCh }, to: { line: i, ch: endCh } },
        true,
      );
      break;
    }
  }
}

export async function highlightParagraph(
  editor: Editor,
  searchText: string,
): Promise<void> {
  const content = editor.getValue();
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes(searchText)) {
      const startCh = line.indexOf(searchText);
      editor.setCursor({ line: i, ch: startCh });
      editor.setSelection({ line: i, ch: startCh }, { line: i, ch: startCh + searchText.length });
      editor.scrollIntoView(
        { from: { line: i, ch: startCh }, to: { line: i, ch: startCh + searchText.length } },
        true,
      );
      break;
    }
  }
}
