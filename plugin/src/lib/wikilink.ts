/** Wikilink preprocessing and click handler */
import type { App } from 'obsidian';
import { openAndHighlight } from './highlight';

/** Preprocess [[wikilink]] to clickable HTML spans */
export function preprocessWikilinks(text: string): string {
  return text.replace(
    /\[\[([^\]]+)\]\]/g,
    '<span class="flamme-wikilink" data-target="$1">$1</span>',
  );
}

/** Handle wikilink click — open note + highlight paragraph */
export function handleWikilinkClick(
  app: App,
  noteName: string,
  sourceText: string | null = null, // The full text that contains the wikilink reference
): void {
  if (!noteName) return;

  // 1. Open the note
  app.workspace.openLinkText(noteName, '', false);

  // 2. If we have the full source text (from LLM response), try to highlight it
  if (sourceText) {
    openAndHighlight(app, noteName, sourceText);
  }
}
