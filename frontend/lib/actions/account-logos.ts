"use server";

import { and, eq, isNull } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts } from "@/lib/db/schema";
import { searchLogo } from "@/lib/actions/logos";

const LOGO_DEV_API_KEY = process.env.LOGO_DEV_API_KEY;

export interface AccountLogoData {
  id: string;
  logoUrl: string | null;
  updatedAt?: Date | null;
}

export interface AccountLogoCandidate {
  id: string;
  institution: string | null;
  logoId: string | null;
  logo?: AccountLogoData | null;
}

function toLogoData(logo: AccountLogoData | null | undefined): AccountLogoData | null {
  if (!logo) {
    return null;
  }

  return {
    id: logo.id,
    logoUrl: logo.logoUrl ?? null,
    updatedAt: logo.updatedAt ?? null,
  };
}

async function getPersistedAccountLogo(accountId: string): Promise<{
  logoId: string | null;
  logo: AccountLogoData | null;
}> {
  const persisted = await db.query.accounts.findFirst({
    where: eq(accounts.id, accountId),
    columns: {
      logoId: true,
    },
    with: {
      logo: {
        columns: {
          id: true,
          logoUrl: true,
          updatedAt: true,
        },
      },
    },
  });

  return {
    logoId: persisted?.logoId ?? null,
    logo: toLogoData(persisted?.logo),
  };
}

async function resolveSingleAccountLogo<T extends AccountLogoCandidate>(
  account: T
): Promise<T & { logoId: string | null; logo: AccountLogoData | null }> {
  if (account.logoId) {
    return {
      ...account,
      logoId: account.logoId,
      logo: toLogoData(account.logo),
    };
  }

  if (!LOGO_DEV_API_KEY || !account.institution?.trim()) {
    return {
      ...account,
      logoId: null,
      logo: null,
    };
  }

  const result = await searchLogo(account.institution.trim());
  if (!result.success || !result.logo) {
    return {
      ...account,
      logoId: null,
      logo: null,
    };
  }

  const now = new Date();
  const [updated] = await db
    .update(accounts)
    .set({
      logoId: result.logo.id,
      updatedAt: now,
    })
    .where(and(eq(accounts.id, account.id), isNull(accounts.logoId)))
    .returning({
      id: accounts.id,
    });

  if (updated) {
    return {
      ...account,
      logoId: result.logo.id,
      logo: toLogoData({
        id: result.logo.id,
        logoUrl: result.logo.logoUrl ?? null,
        updatedAt: result.logo.updatedAt ?? now,
      }),
    };
  }

  const persisted = await getPersistedAccountLogo(account.id);
  return {
    ...account,
    logoId: persisted.logoId,
    logo: persisted.logo,
  };
}

export async function resolveMissingAccountLogos<T extends AccountLogoCandidate>(
  accountsToResolve: T[]
): Promise<Array<T & { logoId: string | null; logo: AccountLogoData | null }>> {
  return Promise.all(accountsToResolve.map((account) => resolveSingleAccountLogo(account)));
}

export async function resolveMissingAccountLogo<T extends AccountLogoCandidate>(
  account: T
): Promise<T & { logoId: string | null; logo: AccountLogoData | null }> {
  return resolveSingleAccountLogo(account);
}
