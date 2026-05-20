import JSZip from "jszip";

export type EpubTocItem = {
  id: string;
  label: string;
  href: string;
  depth: number;
};

const CHAPTER_HEADING_RE =
  /(?:Prologue|Epilogue|Appendix|Chapter\s+(?:(?:Twenty|Thirty|Forty|Fifty|Sixty|Seventy|Eighty|Ninety)\s+)?(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen)(?:\s+(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine))?(?:\s+[A-Z][a-z']+)?)/;

const CONTENT_MAP_TITLE_RE =
  /(?:Prologue|Epilogue|Appendix|Chapter\s+(?:(?:Twenty|Thirty|Forty|Fifty|Sixty|Seventy|Eighty|Ninety)\s+)?(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen)(?:\s+(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine))?(?:\s+[A-Z][a-z']+)?)/g;

const NUMBER_WORDS: Record<string, number> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  eleven: 11,
  twelve: 12,
  thirteen: 13,
  fourteen: 14,
  fifteen: 15,
  sixteen: 16,
  seventeen: 17,
  eighteen: 18,
  nineteen: 19,
  twenty: 20,
  thirty: 30,
  forty: 40,
  fifty: 50,
  sixty: 60,
  seventy: 70,
  eighty: 80,
  ninety: 90,
};

const CHAPTER_LABEL_RE =
  /^Chapter\s+((?:(?:Twenty|Thirty|Forty|Fifty|Sixty|Seventy|Eighty|Ninety)\s+)?(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen)(?:\s+(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine))?)(?:\s+(.*))?$/i;

function wordsToNumber(words: string): number | null {
  let total = 0;
  for (const part of words.toLowerCase().trim().split(/\s+/)) {
    const value = NUMBER_WORDS[part];
    if (value === undefined) return null;
    total += value;
  }
  return total > 0 ? total : null;
}

function toRoman(n: number): string {
  if (n < 1 || n > 399) return String(n);
  const pairs: [number, string][] = [
    [100, "C"],
    [90, "XC"],
    [50, "L"],
    [40, "XL"],
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let num = n;
  let out = "";
  for (const [value, numeral] of pairs) {
    while (num >= value) {
      out += numeral;
      num -= value;
    }
  }
  return out;
}

/** "Chapter One Bran" → "Chapter I Bran" */
export function formatChapterLabel(label: string): string {
  const m = label.match(CHAPTER_LABEL_RE);
  if (!m) return label;
  const num = wordsToNumber(m[1]);
  if (num === null) return label;
  const suffix = m[2]?.trim();
  return suffix ? `Chapter ${toRoman(num)} ${suffix}` : `Chapter ${toRoman(num)}`;
}

function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isSkippableSpineSection(text: string, href: string): boolean {
  if (/titlepage|cover/i.test(href)) return true;
  if (/Content Map/i.test(text)) return true;
  if (/\bMap\s*\((?:North|South)\)/i.test(text) && !/Chapter\s+/i.test(text)) {
    return true;
  }
  return text.replace(/\s+/g, " ").trim().length < 500;
}

function labelFromText(text: string): string | null {
  if (!text || /Content Map/i.test(text)) return null;
  if (/\bMap\s*\((?:North|South)\)/i.test(text) && !/Chapter\s+/i.test(text)) {
    return null;
  }

  const m = text.match(CHAPTER_HEADING_RE);
  if (m) {
    return formatChapterLabel(m[0].trim().replace(/\s+The$/, ""));
  }
  return null;
}

function parseContentMapTitles(text: string): string[] {
  if (!/Content Map/i.test(text)) return [];
  const titles: string[] = [];
  let m: RegExpExecArray | null;
  CONTENT_MAP_TITLE_RE.lastIndex = 0;
  while ((m = CONTENT_MAP_TITLE_RE.exec(text)) !== null) {
    titles.push(formatChapterLabel(m[0].replace(/\s+The$/, "").trim()));
  }
  return titles;
}

function findOpfPath(containerXml: string): string | null {
  const m = containerXml.match(/full-path="([^"]+\.opf)"/i);
  return m?.[1] ?? null;
}

function parseSpineHrefs(opfXml: string): string[] {
  const manifest: Record<string, string> = {};
  for (const m of opfXml.matchAll(/<item\s+[^>]*\/?>/gi)) {
    const tag = m[0];
    const id = tag.match(/\bid="([^"]+)"/i)?.[1];
    const href = tag.match(/\bhref="([^"]+)"/i)?.[1];
    if (id && href) manifest[id] = href;
  }
  const hrefs: string[] = [];
  for (const m of opfXml.matchAll(/<itemref\s+[^>]*idref="([^"]+)"/gi)) {
    const href = manifest[m[1]];
    if (href) hrefs.push(href);
  }
  return hrefs;
}

async function readZipText(zip: JSZip, path: string): Promise<string | null> {
  const file = zip.file(path) ?? zip.file(path.replace(/^\//, ""));
  if (!file) return null;
  return file.async("text");
}

/** Build TOC from raw EPUB bytes (works without epub.js section loading). */
export async function buildTocFromEpubBuffer(data: ArrayBuffer): Promise<EpubTocItem[]> {
  const zip = await JSZip.loadAsync(data);

  const containerXml = await readZipText(zip, "META-INF/container.xml");
  if (!containerXml) return [];

  const opfPath = findOpfPath(containerXml);
  if (!opfPath) return [];

  const opfXml = await readZipText(zip, opfPath);
  if (!opfXml) return [];

  const spineHrefs = parseSpineHrefs(opfXml);
  let pendingTitles: string[] = [];
  const out: EpubTocItem[] = [];
  let titleIdx = 0;

  for (const href of spineHrefs) {
    const html = await readZipText(zip, href);
    if (!html) continue;

    const text = stripHtml(html);
    if (!text) continue;

    if (/Content Map/i.test(text)) {
      pendingTitles = parseContentMapTitles(text);
      continue;
    }
    if (isSkippableSpineSection(text, href)) continue;

    let label: string | null = null;
    if (pendingTitles.length > 0 && titleIdx < pendingTitles.length) {
      label = pendingTitles[titleIdx];
      titleIdx += 1;
    } else {
      label = labelFromText(text);
    }
    if (!label) continue;

    out.push({
      id: href,
      label: formatChapterLabel(label),
      href,
      depth: 0,
    });
  }

  return out;
}
