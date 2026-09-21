const ID_PATTERNS = [
  /\bCUST-\d+\b/gi,
  /\bPAS-[A-Z]{3}-\d+\b/gi,
  /\bRAW-[A-Z]{3}-\d+\b/gi,
  /\bL-\d+\b/gi,
  /\bDOC-\d+\b/gi,
  /\bSUP-\d+\b/gi,
  /\bCALL-\d+\b/gi,
];

export function extractEntityIds(text: string): string[] {
  const found = new Set<string>();
  for (const pattern of ID_PATTERNS) {
    const re = new RegExp(pattern.source, pattern.flags);
    for (const match of text.matchAll(re)) {
      found.add(match[0].toUpperCase());
    }
  }
  return [...found];
}

export function inferConfidence(
  answer: string,
  sources: string[],
): { label: string; value: number } {
  const lower = answer.toLowerCase();
  if (
    lower.includes("not available") ||
    lower.includes("cannot answer") ||
    lower.includes("temporarily unavailable")
  ) {
    return { label: "Low — limited evidence", value: 25 };
  }
  if (sources.length >= 2) {
    return { label: "High — multi-source", value: 88 };
  }
  if (sources.length === 1) {
    return { label: "Medium — single source", value: 62 };
  }
  return { label: "Medium", value: 50 };
}

export function isHtmlAnswer(answer: string): boolean {
  const trimmed = answer.trim();
  return (
    trimmed.startsWith("<") &&
    (trimmed.includes("</") || trimmed.includes("/>"))
  );
}
