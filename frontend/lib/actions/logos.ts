"use server";

import { eq, or, ilike } from "drizzle-orm";
import { db } from "@/lib/db";
import { companyLogos, type CompanyLogo, type NewCompanyLogo } from "@/lib/db/schema";
import { storage } from "@/lib/storage";

// ============================================================================
// Constants
// ============================================================================

const NOT_FOUND_RECHECK_DAYS = 30;

function getLogoDevApiKey(): string | undefined {
  // Use bracket access to avoid build-time env inlining in Next.js server bundles.
  return process.env["LOGO_DEV_API_KEY"];
}

async function upsertLogoByDomain(
  logoData: NewCompanyLogo
): Promise<CompanyLogo | null> {
  if (!logoData.domain) {
    return null;
  }

  const [upserted] = await db
    .insert(companyLogos)
    .values(logoData)
    .onConflictDoUpdate({
      target: companyLogos.domain,
      set: {
        companyName: logoData.companyName ?? null,
        logoUrl: logoData.logoUrl ?? null,
        status: logoData.status ?? "found",
        lastCheckedAt: logoData.lastCheckedAt ?? new Date(),
        updatedAt: logoData.updatedAt ?? new Date(),
      },
    })
    .returning();

  if (upserted) {
    return upserted;
  }

  return (
    (await db.query.companyLogos.findFirst({
      where: eq(companyLogos.domain, logoData.domain),
    })) || null
  );
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Derives a domain from a company name.
 * Examples:
 *   "Netflix" -> "netflix.com"
 *   "Spotify Premium" -> "spotify.com"
 *   "Apple Inc" -> "apple.com"
 */
function deriveDomainFromName(name: string): string {
  // Remove common suffixes
  const suffixes = [
    "inc",
    "inc.",
    "ltd",
    "ltd.",
    "llc",
    "llc.",
    "corp",
    "corp.",
    "corporation",
    "company",
    "co",
    "co.",
    "gmbh",
    "ag",
    "bv",
    "premium",
    "plus",
    "pro",
    "basic",
    "subscription",
    "annual",
    "monthly",
  ];

  let cleaned = name.toLowerCase().trim();

  // Remove suffixes
  for (const suffix of suffixes) {
    const regex = new RegExp(`\\s+${suffix}$`, "i");
    cleaned = cleaned.replace(regex, "");
  }

  // Remove special characters and extra spaces
  cleaned = cleaned
    .replace(/[^\w\s]/g, "")
    .replace(/\s+/g, "")
    .trim();

  return `${cleaned}.com`;
}

/**
 * Check if a "not_found" entry should be rechecked (older than 30 days)
 */
function shouldRecheckNotFound(logo: CompanyLogo): boolean {
  if (logo.status !== "not_found" || !logo.lastCheckedAt) {
    return false;
  }

  const daysSinceCheck = Math.floor(
    (Date.now() - new Date(logo.lastCheckedAt).getTime()) / (1000 * 60 * 60 * 24)
  );

  return daysSinceCheck >= NOT_FOUND_RECHECK_DAYS;
}

/**
 * Fetch logo from Logo.dev API and store locally
 */
async function fetchAndStoreLogo(
  domain: string
): Promise<{ success: boolean; logoUrl?: string }> {
  const logoDevApiKey = getLogoDevApiKey();
  if (!logoDevApiKey) {
    console.error("LOGO_DEV_API_KEY is not configured");
    return { success: false };
  }

  try {
    const apiUrl = `https://img.logo.dev/${domain}?token=${logoDevApiKey}&size=128&format=png`;

    const response = await fetch(apiUrl);

    if (!response.ok) {
      console.log(`Logo not found for domain: ${domain}`);
      return { success: false };
    }

    // Check content type - Logo.dev returns a placeholder for unknown domains
    const contentType = response.headers.get("content-type");
    if (!contentType?.includes("image")) {
      return { success: false };
    }

    // Download the image
    const imageBuffer = Buffer.from(await response.arrayBuffer());

    // Check if image is too small (likely a placeholder)
    if (imageBuffer.length < 1000) {
      return { success: false };
    }

    // Store locally using the storage provider
    const fileName = `logos/${domain.replace(/[^a-z0-9.-]/gi, "_")}.png`;
    const uploadedFile = await storage.upload(fileName, imageBuffer, {
      contentType: "image/png",
    });

    return { success: true, logoUrl: uploadedFile.url };
  } catch (error) {
    console.error(`Failed to fetch logo for ${domain}:`, error);
    return { success: false };
  }
}

// ============================================================================
// Public Actions
// ============================================================================

/**
 * Check if the Logo.dev API key is configured
 */
export async function hasLogoApiKey(): Promise<boolean> {
  return !!getLogoDevApiKey();
}

/**
 * Search for a company logo by domain or name.
 * Checks the cache first, fetches from Logo.dev API if not found.
 */
export async function searchLogo(
  query: string
): Promise<{
  success: boolean;
  error?: string;
  logo?: CompanyLogo;
}> {
  if (!query?.trim()) {
    return { success: false, error: "Query is required" };
  }

  const trimmedQuery = query.trim().toLowerCase();

  // Determine if query is a domain or a name
  const isDomain = trimmedQuery.includes(".");
  const domain = isDomain ? trimmedQuery : deriveDomainFromName(trimmedQuery);
  const companyName = isDomain ? trimmedQuery.split(".")[0] : trimmedQuery;

  try {
    // Check if logo exists in cache
    const existingLogo = await db.query.companyLogos.findFirst({
      where: eq(companyLogos.domain, domain),
    });

    // If found and status is "found", return cached
    if (existingLogo && existingLogo.status === "found") {
      return { success: true, logo: existingLogo };
    }

    // If found with "not_found" and not old enough, return null (skip API)
    if (existingLogo && existingLogo.status === "not_found") {
      if (!shouldRecheckNotFound(existingLogo)) {
        return { success: true, logo: undefined };
      }
    }

    // Fetch from Logo.dev API
    const fetchResult = await fetchAndStoreLogo(domain);

    if (fetchResult.success && fetchResult.logoUrl) {
      // Insert or update with found status
      const logoData: NewCompanyLogo = {
        domain,
        companyName,
        logoUrl: fetchResult.logoUrl,
        status: "found",
        lastCheckedAt: new Date(),
        updatedAt: new Date(),
      };
      const upserted = await upsertLogoByDomain(logoData);
      return { success: true, logo: upserted || undefined };
    } else {
      // Mark as not_found
      const logoData: NewCompanyLogo = {
        domain,
        companyName,
        logoUrl: null,
        status: "not_found",
        lastCheckedAt: new Date(),
        updatedAt: new Date(),
      };
      await upsertLogoByDomain(logoData);

      return { success: true, logo: undefined };
    }
  } catch (error) {
    console.error("Failed to search logo:", error);
    return { success: false, error: "Failed to search for logo" };
  }
}

/**
 * Get a logo by its ID
 */
export async function getLogoById(id: string): Promise<CompanyLogo | null> {
  if (!id) {
    return null;
  }

  try {
    const logo = await db.query.companyLogos.findFirst({
      where: eq(companyLogos.id, id),
    });

    return logo || null;
  } catch (error) {
    console.error("Failed to get logo by ID:", error);
    return null;
  }
}

/**
 * Get a logo by domain
 */
export async function getLogoByDomain(domain: string): Promise<CompanyLogo | null> {
  if (!domain?.trim()) {
    return null;
  }

  try {
    const logo = await db.query.companyLogos.findFirst({
      where: eq(companyLogos.domain, domain.toLowerCase().trim()),
    });

    // Only return if status is "found"
    if (logo && logo.status === "found") {
      return logo;
    }

    return null;
  } catch (error) {
    console.error("Failed to get logo by domain:", error);
    return null;
  }
}

/**
 * Search logos in the database by name (for autocomplete)
 */
export async function searchLogosInCache(
  query: string,
  limit = 5
): Promise<CompanyLogo[]> {
  if (!query?.trim()) {
    return [];
  }

  try {
    const logos = await db.query.companyLogos.findMany({
      where: or(
        ilike(companyLogos.domain, `%${query}%`),
        ilike(companyLogos.companyName, `%${query}%`)
      ),
      limit,
    });

    // Only return logos with status "found"
    return logos.filter((l) => l.status === "found");
  } catch (error) {
    console.error("Failed to search logos in cache:", error);
    return [];
  }
}
