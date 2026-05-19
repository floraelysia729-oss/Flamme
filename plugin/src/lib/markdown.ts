/** Markdown + KaTeX + wikilink rendering */
import { Marked } from 'marked';

const marked = new Marked({
  gfm: true,
  breaks: true,
});

export function extractSuggestionQuestions(text: string): { questions: string[]; cleanText: string } {
  const match = text.match(/(?:^|\n)\s*(?:\*\*)?(?:__)?SUGGESTIONS(?:__)?(?:\*\*)?\s*[:：]\s*(\[[\s\S]*?\])\s*$/i);
  if (!match) return { questions: [], cleanText: text };

  try {
    const normalized = match[1].replace(/["\u201C\u201D]/g, '"').replace(/['\u2018\u2019]/g, "'");
    const parsed = JSON.parse(normalized);
    if (Array.isArray(parsed)) {
      const questions = parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
      if (questions.length > 0) {
        return {
          questions,
          cleanText: text.slice(0, match.index).trim(),
        };
      }
    }
  } catch {
    // If parsing fails, keep the original text so the model output is not lost.
  }

  return { questions: [], cleanText: text };
}

/** Preprocess [[wikilink]] → clickable HTML spans */
export function preprocessWikilinks(text: string): string {
  return text.replace(
    /\[\[([^\]]+)\]\]/g,
    '<span class="flamme-wikilink" data-target="$1">$1</span>',
  );
}

/** Render message content: markdown + math + wikilinks */
export function renderMarkdown(text: string): string {
  if (!text) return '';

  const { cleanText: cleanedText } = extractSuggestionQuestions(text);

  // Step 1: Preprocess wikilinks before markdown parsing
  const withWikilinks = preprocessWikilinks(cleanedText);

  // Step 2: Extract and protect code blocks (so LaTeX inside code isn't processed)
  const codeBlocks: string[] = [];
  let protectedText = withWikilinks;

  // Fenced code blocks (```...```)
  protectedText = protectedText.replace(/```[\s\S]*?```/g, (match) => {
    const idx = codeBlocks.length;
    codeBlocks.push(match);
    return `\x00CODEBLOCK${idx}\x00`;
  });

  // Inline code (`...`)
  protectedText = protectedText.replace(/`([^`\n]+)`/g, (match) => {
    const idx = codeBlocks.length;
    codeBlocks.push(match);
    return `\x00CODEBLOCK${idx}\x00`;
  });

  // Step 3: Extract and render math blocks
  // Block math $$...$$
  protectedText = protectedText.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    try {
      const rendered = renderKaTeX(math.trim(), true);
      return `<div class="flamme-math-block">${rendered}</div>`;
    } catch {
      return `<code class="math-error">${escapeHtml(math.trim())}</code>`;
    }
  });

  // Inline math $...$
  protectedText = protectedText.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    try {
      const rendered = renderKaTeX(math.trim(), false);
      return `<span class="flamme-math-inline">${rendered}</span>`;
    } catch {
      return `<code class="math-error">${escapeHtml(math.trim())}</code>`;
    }
  });

  // Step 4: Restore code blocks
  protectedText = protectedText.replace(/\x00CODEBLOCK(\d+)\x00/g, (_, idx) => {
    return codeBlocks[parseInt(idx)];
  });

  // Step 5: Render markdown
  let html = marked.parse(protectedText) as string;

  return html;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderKaTeX(math: string, displayMode: boolean): string {
  try {
    // KaTeX is loaded synchronously via the bundle
    const katex = require('katex');
    return katex.renderToString(math, { displayMode, throwOnError: false });
  } catch {
    return `<code>${escapeHtml(math)}</code>`;
  }
}
