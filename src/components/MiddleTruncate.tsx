/**
 * @file    src/components/MiddleTruncate.tsx
 * @purpose Text component that truncates long file paths in the middle
 *          (preserving start and end) to fit available space.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

interface MiddleTruncateProps {
  text: string;
  /** Anzahl der am Ende garantiert sichtbaren Zeichen (z.B. Dateiendung). */
  tailLength?: number;
  className?: string;
}

/** Kürzt langen Text in der Mitte ("langer…name.pdf") statt am Ende, damit
 * sowohl der Anfang als auch das Ende (z.B. die Dateiendung) sichtbar
 * bleiben. Der vollständige Text erscheint als Tooltip.
 *
 * Reiner CSS-Trick statt Pixel-Messung: der Kopf-Teil steckt in einer
 * "truncate"-Flex-Zelle (ellipsis am Ende), der feste Endteil (tailLength
 * Zeichen) folgt in einer nicht schrumpfenden Zelle - der Browser
 * berechnet die Kürzung dadurch automatisch anhand der verfügbaren Breite,
 * ohne dass hier Spaltenbreiten in Pixel bekannt sein müssen. */
export function MiddleTruncate({ text, tailLength = 10, className = "" }: MiddleTruncateProps) {
  const shouldSplit = text.length > tailLength + 4;
  const head = shouldSplit ? text.slice(0, text.length - tailLength) : text;
  const tail = shouldSplit ? text.slice(-tailLength) : "";

  return (
    <span title={text} className={`flex min-w-0 ${className}`}>
      <span className="truncate">{head}</span>
      {tail && <span className="shrink-0">{tail}</span>}
    </span>
  );
}
