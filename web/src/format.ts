export const num = (v: number, digits = 2) =>
  v.toLocaleString("zh-TW", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Metres, shown the way a drawing would: metres above 1 m, millimetres below. */
export function length(m: number): string {
  if (!isFinite(m)) return "—";
  if (Math.abs(m) < 1) return `${num(m * 1000, 0)} mm`;
  return `${num(m, 3)} m`;
}

export const area = (m2: number) => `${num(m2, 2)} m²`;

export const bytes = (n: number) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${num(n / 1024, 0)} KB`;
  if (n < 1024 ** 3) return `${num(n / 1024 ** 2, 1)} MB`;
  return `${num(n / 1024 ** 3, 2)} GB`;
};

export const when = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("zh-TW", { hour12: false });
};

export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const escape = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const body = rows.map((r) => r.map(escape).join(",")).join("\r\n");
  // BOM so Excel on Windows opens the Chinese columns as UTF-8.
  const blob = new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
