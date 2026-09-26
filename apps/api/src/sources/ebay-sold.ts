import * as cheerio from "cheerio";
import type { CardIdentityRow, SourcedObservation } from "./types.js";

/**
 * eBay "Sold items" result-page parser (source: ebay_sold_scrape, licence status: unlicensed).
 *
 * Input is the HTML of an eBay search-results page filtered to sold items
 * (…/sch/i.html?_nkw=…&LH_Sold=1&LH_Complete=1). Both the older `li.s-item` and the newer
 * `li.s-card` result markup are handled, using text heuristics rather than deep selectors so
 * that minor markup changes do not silently corrupt prices.
 */

export interface EbaySoldListing {
  itemId: string;
  url: string | null;
  title: string;
  soldDate: string | null;
  priceText: string;
  amountMinor: number | null;
  currency: string | null;
  bestOfferAccepted: boolean;
  priceIsRange: boolean;
}

const MONTHS: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
};

/** Parse "Sold Sep 20, 2026" (US) or "Sold 20 Sep 2026" (UK/AU). */
export function parseSoldDate(text: string): string | null {
  const t = text.replace(/\s+/g, " ");
  const us = /Sold\s+([A-Za-z]{3,4})\.?\s+(\d{1,2}),?\s+(\d{4})/i.exec(t);
  const intl = /Sold\s+(\d{1,2})\s+([A-Za-z]{3,4})\.?,?\s+(\d{4})/i.exec(t);
  let y: number, m: number | undefined, d: number;
  if (us) {
    m = MONTHS[us[1]!.toLowerCase()];
    d = Number(us[2]);
    y = Number(us[3]);
  } else if (intl) {
    m = MONTHS[intl[2]!.toLowerCase()];
    d = Number(intl[1]);
    y = Number(intl[3]);
  } else {
    return null;
  }
  if (!m || d < 1 || d > 31) return null;
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

const CURRENCY_PREFIXES: Array<[RegExp, string]> = [
  [/^AU\s?\$/i, "AUD"],
  [/^C\s?\$/i, "CAD"],
  [/^NZ\s?\$/i, "NZD"],
  [/^US\s?\$/i, "USD"],
  [/^£|^GBP/i, "GBP"],
  [/^€|^EUR/i, "EUR"],
  [/^\$/, "USD"],
];

/** Parse "$1,234.56", "AU $99.00", "EUR 12,50", "£8.00". Ranges ("$10.00 to $20.00") return null. */
export function parsePrice(text: string, fallbackCurrency: string): { amountMinor: number | null; currency: string | null; isRange: boolean } {
  const t = text.replace(/\s+/g, " ").trim();
  if (/\bto\b/i.test(t)) return { amountMinor: null, currency: null, isRange: true };
  let currency: string | null = null;
  for (const [re, code] of CURRENCY_PREFIXES) {
    if (re.test(t)) {
      currency = code;
      break;
    }
  }
  const num = /(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)/.exec(t.replace(/^[^\d]*/, ""));
  if (!num) return { amountMinor: null, currency, isRange: false };
  let raw = num[1]!.replace(/\s/g, "");
  // Decimal separator is the last '.' or ',' when followed by exactly two digits.
  const decimal = /[.,](\d{2})$/.exec(raw);
  const whole = decimal ? raw.slice(0, -3) : raw;
  raw = whole.replace(/[.,]/g, "") + (decimal ? `.${decimal[1]}` : "");
  const value = Number(raw);
  if (!Number.isFinite(value)) return { amountMinor: null, currency, isRange: false };
  return { amountMinor: Math.round(value * 100), currency: currency ?? fallbackCurrency, isRange: false };
}

export function parseEbaySoldPage(html: string, fallbackCurrency = "USD"): EbaySoldListing[] {
  const $ = cheerio.load(html);
  const out: EbaySoldListing[] = [];
  const seen = new Set<string>();
  $("li.s-item, li.s-card").each((_, el) => {
    const item = $(el);
    const link = item.find("a[href*='/itm/']").first().attr("href") ?? null;
    const itemId = (link && /\/itm\/(?:[^/?]*\/)?(\d{9,15})/.exec(link)?.[1]) ?? item.attr("data-listingid") ?? item.attr("id")?.replace(/\D/g, "") ?? "";
    const title = item
      .find(".s-item__title, .s-card__title")
      .first()
      .text()
      .replace(/^New Listing/i, "")
      .replace(/Opens in a new window or tab$/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!itemId || !title || /^shop on ebay$/i.test(title) || seen.has(itemId)) return;
    seen.add(itemId);
    const text = item.text().replace(/\s+/g, " ");
    const priceEl = item.find(".s-item__price, .s-card__price").first();
    const priceText = priceEl.text().replace(/\s+/g, " ").trim();
    const struck = priceEl.find(".STRIKETHROUGH, s, del").length > 0 || priceEl.is(".STRIKETHROUGH");
    const price = parsePrice(priceText, fallbackCurrency);
    out.push({
      itemId,
      url: link ? link.split("?")[0]! : null,
      title,
      soldDate: parseSoldDate(text),
      priceText,
      amountMinor: price.amountMinor,
      currency: price.currency,
      bestOfferAccepted: struck || /best offer accepted/i.test(text),
      priceIsRange: price.isRange,
    });
  });
  return out;
}

const GRADERS = ["PSA", "BGS", "CGC", "SGC", "TAG", "ACE"];
const EXCLUDE = /\b(lot|lots|bundle|bulk|proxy|custom|orica|replica|reprint|fake|digital|code card|empty|slab only|no card|playmat|sleeves?|binder|x[2-9]|[2-9]x)\b/i;
const LANGUAGES: Array<[RegExp, string]> = [
  [/\b(japanese|japan|jpn|jp)\b/i, "ja"],
  [/\b(korean|kor)\b/i, "ko"],
  [/\b(chinese|chn|s-chinese|t-chinese)\b/i, "zh"],
  [/\b(german|deutsch)\b/i, "de"],
  [/\b(french|français|francais)\b/i, "fr"],
  [/\b(italian|italiano)\b/i, "it"],
  [/\b(spanish|español|espanol)\b/i, "es"],
  [/\b(portuguese)\b/i, "pt"],
];

/** "PSA 10 candidate", "PSA ready" etc. describe raw cards — strip before parsing a grade. */
const RAW_GRADE_HYPE = /\b(PSA|BGS|CGC|SGC|TAG|ACE)\s*(10|[1-9](\.5)?)?\s*(candidate|ready|worthy|potential|contender)\b/gi;

export function parseGrading(title: string): { gradingCompany: string | null; grade: string | null } {
  const t = title.replace(RAW_GRADE_HYPE, " ").replace(/beckett/i, "BGS");
  const re = new RegExp(`\\b(${GRADERS.join("|")})\\b[^0-9]{0,20}?(10|[1-9](?:\\.5)?)\\b`, "i");
  const m = re.exec(t);
  if (m) return { gradingCompany: m[1]!.toUpperCase(), grade: m[2]! };
  return { gradingCompany: null, grade: null };
}

/** Raw condition stated in a title, if any (eBay item specifics are not on the results page). */
export function parseCondition(title: string): string | null {
  if (/\b(near\s*mint|nm(\/m|-m|\+)?)\b/i.test(title)) return "NM";
  if (/\b(lightly\s*played|lp)\b/i.test(title)) return "LP";
  if (/\b(moderately\s*played|mp)\b/i.test(title)) return "MP";
  if (/\b(heavily\s*played|hp)\b/i.test(title)) return "HP";
  if (/\b(damaged|dmg)\b/i.test(title)) return "DMG";
  if (/\bmint\b/i.test(title)) return "M";
  return null;
}

function numberPatterns(cardNumber: string): RegExp {
  const [num, total] = cardNumber.split("/");
  if (total !== undefined) {
    const n = num!.replace(/^0+(?=\d)/, "");
    return new RegExp(`(?:\\b0*${n}\\s*/\\s*0*${total.replace(/^0+(?=\d)/, "")}\\b|#\\s*0*${n}\\b)`, "i");
  }
  return new RegExp(`\\b${cardNumber.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&")}\\b`, "i");
}

export type MatchSkipReason =
  | "no_sold_date"
  | "no_price"
  | "price_range"
  | "excluded_term"
  | "name_mismatch"
  | "number_mismatch"
  | "language_mismatch"
  | "edition_mismatch";

/** Decide whether a scraped listing title describes the catalogue identity. Grading is parsed, not required. */
export function matchListing(
  identity: Pick<CardIdentityRow, "card_name" | "card_number" | "language" | "edition" | "product_type">,
  listing: EbaySoldListing,
): { matched: true; gradingCompany: string | null; grade: string | null; condition: string | null } | { matched: false; reason: MatchSkipReason } {
  if (!listing.soldDate) return { matched: false, reason: "no_sold_date" };
  if (listing.priceIsRange) return { matched: false, reason: "price_range" };
  if (listing.amountMinor == null || !listing.currency) return { matched: false, reason: "no_price" };
  const title = listing.title;
  if (EXCLUDE.test(title)) return { matched: false, reason: "excluded_term" };

  const nameTokens = identity.card_name
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1);
  const lowerTitle = title.toLowerCase();
  if (!nameTokens.every((t) => lowerTitle.includes(t))) return { matched: false, reason: "name_mismatch" };
  if (identity.card_number && !numberPatterns(identity.card_number).test(title)) return { matched: false, reason: "number_mismatch" };

  const titleLang = LANGUAGES.find(([re]) => re.test(title))?.[1] ?? "en";
  if (titleLang !== identity.language) return { matched: false, reason: "language_mismatch" };

  const first = /\b(1st\s*ed(ition)?|first\s*edition)\b/i.test(title);
  const shadowless = /\bshadowless\b/i.test(title);
  const edition = (identity.edition ?? "").toLowerCase();
  const wantFirst = /1st|first/.test(edition);
  const wantShadowless = /shadowless/.test(edition);
  if (first !== wantFirst || shadowless !== wantShadowless) return { matched: false, reason: "edition_mismatch" };

  if (identity.product_type === "sealed") return { matched: true, gradingCompany: null, grade: null, condition: "sealed" };
  const grading = parseGrading(title);
  return { matched: true, ...grading, condition: grading.gradingCompany ? null : parseCondition(title) };
}

export interface ParsedImport {
  observations: SourcedObservation[];
  listingsFound: number;
  skipped: Partial<Record<MatchSkipReason, number>>;
}

export function ebayPageToObservations(
  html: string,
  identity: CardIdentityRow,
  opts: { fallbackCurrency?: string; site?: string } = {},
): ParsedImport {
  const listings = parseEbaySoldPage(html, opts.fallbackCurrency ?? "USD");
  const skipped: ParsedImport["skipped"] = {};
  const observations: SourcedObservation[] = [];
  for (const l of listings) {
    const m = matchListing(identity, l);
    if (!m.matched) {
      skipped[m.reason] = (skipped[m.reason] ?? 0) + 1;
      continue;
    }
    observations.push({
      sourceReference: `ebay:${l.itemId}`,
      sourceUrl: l.url ?? `https://www.${opts.site ?? "ebay.com"}/itm/${l.itemId}`,
      kind: "completed_sale",
      gradingCompany: m.gradingCompany,
      grade: m.grade,
      condition: m.condition,
      observedAt: l.soldDate!,
      venue: `eBay (${opts.site ?? "ebay.com"})`,
      amountMinor: l.amountMinor!,
      currency: l.currency!,
      buyersPremiumMinor: 0,
      // eBay sales between unrelated parties are presumed arm's length.
      armsLength: true,
      verificationStatus: l.bestOfferAccepted ? "unverified" : "verified",
      verificationNotes: l.bestOfferAccepted
        ? "UNLICENSED/SCRAPED. Best offer accepted: the price shown is the struck-through asking price, not the sale price."
        : "UNLICENSED/SCRAPED. Marked 'Sold' on eBay result page; not independently verified.",
      raw: { title: l.title, priceText: l.priceText, soldDate: l.soldDate, bestOfferAccepted: l.bestOfferAccepted, itemId: l.itemId },
    });
  }
  return { observations, listingsFound: listings.length, skipped };
}
