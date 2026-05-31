"use client";

import { useEffect, useState } from "react";
import { PersonAvatar } from "./person-avatar";
import type { EntityType } from "@/lib/people";

type Person = {
  id: string;
  name: string;
  color?: string | null;
  avatarUrl?: string | null;
};

type OwnerRow = { personId: string; share: number | null };

type CacheEntry<T> = { value: T; timestamp: number };
const TTL_MS = 30_000;

const peopleCache: { entry?: CacheEntry<Person[]> } = {};
const ownersCache = new Map<string, CacheEntry<OwnerRow[]>>();

function isFresh<T>(e: CacheEntry<T> | undefined): e is CacheEntry<T> {
  return !!e && Date.now() - e.timestamp < TTL_MS;
}

export function clearOwnerBadgesCache() {
  peopleCache.entry = undefined;
  ownersCache.clear();
}

async function loadPeople(): Promise<Person[]> {
  if (isFresh(peopleCache.entry)) return peopleCache.entry.value;
  try {
    const r = await fetch("/api/people");
    if (!r.ok) return [];
    const j = await r.json();
    if (!Array.isArray(j?.people)) return [];
    peopleCache.entry = { value: j.people, timestamp: Date.now() };
    return j.people;
  } catch {
    return [];
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Batched owner loader.
// Multiple <OwnerBadges> mounted together (e.g. on a list page) coalesce
// their lookups into a single POST /api/owners/batch round trip per
// microtask tick, instead of N parallel GETs.
// ──────────────────────────────────────────────────────────────────────────

type Pending = { resolvers: ((rows: OwnerRow[]) => void)[] };
const pending = new Map<string, Pending>();
let scheduled = false;

function scheduleFlush() {
  if (scheduled) return;
  scheduled = true;
  // Microtask gives every same-tick mount a chance to enqueue before we send.
  queueMicrotask(flush);
}

async function flush() {
  scheduled = false;
  if (pending.size === 0) return;

  const batch = Array.from(pending.entries());
  pending.clear();

  const byType: Record<EntityType, Set<string>> = {
    account: new Set(),
    property: new Set(),
    vehicle: new Set(),
  };
  for (const [key] of batch) {
    const [t, id] = key.split(":") as [EntityType, string];
    byType[t].add(id);
  }

  let data: Partial<Record<EntityType, Record<string, OwnerRow[]>>> = {};
  try {
    const r = await fetch("/api/owners/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account: Array.from(byType.account),
        property: Array.from(byType.property),
        vehicle: Array.from(byType.vehicle),
      }),
    });
    if (r.ok) data = await r.json();
  } catch {
    // Ignore — resolvers below will get [] and the badges silently won't render.
  }

  for (const [key, p] of batch) {
    const [t, id] = key.split(":") as [EntityType, string];
    const owners = data[t]?.[id] ?? [];
    ownersCache.set(key, { value: owners, timestamp: Date.now() });
    for (const r of p.resolvers) r(owners);
  }
}

function loadOwners(entityType: EntityType, entityId: string): Promise<OwnerRow[]> {
  const key = `${entityType}:${entityId}`;
  const fresh = ownersCache.get(key);
  if (isFresh(fresh)) return Promise.resolve(fresh.value);
  return new Promise((resolve) => {
    const slot = pending.get(key) ?? { resolvers: [] };
    slot.resolvers.push(resolve);
    pending.set(key, slot);
    scheduleFlush();
  });
}

/**
 * Renders a stacked-avatar row of the people who own this entity.
 * Hidden in single-person households (only one person total).
 *
 * Pass `people` and `ownerIds` to skip the client fetch entirely — list pages
 * preload these server-side to avoid even the batched round trip.
 */
export function OwnerBadges({
  entityType,
  entityId,
  size = 24,
  max = 3,
  people: peopleProp,
  ownerIds: ownerIdsProp,
}: {
  entityType: EntityType;
  entityId: string;
  size?: number;
  max?: number;
  people?: Person[];
  ownerIds?: string[];
}) {
  const preloaded = peopleProp !== undefined && ownerIdsProp !== undefined;
  const [people, setPeople] = useState<Person[]>(peopleProp ?? []);
  const [ownerIds, setOwnerIds] = useState<string[]>(ownerIdsProp ?? []);

  useEffect(() => {
    if (preloaded) {
      setPeople(peopleProp!);
      setOwnerIds(ownerIdsProp!);
      return;
    }
    let cancelled = false;
    Promise.all([loadPeople(), loadOwners(entityType, entityId)]).then(
      ([all, owners]) => {
        if (cancelled) return;
        setPeople(all);
        setOwnerIds(owners.map((o) => o.personId));
      }
    );
    return () => {
      cancelled = true;
    };
  }, [entityType, entityId, preloaded, peopleProp, ownerIdsProp]);

  if (people.length < 2) return null;
  const owners = people.filter((p) => ownerIds.includes(p.id));
  if (owners.length === 0) return null;

  const visible = owners.slice(0, max);
  const overflow = owners.length - visible.length;

  return (
    <div className="flex items-center -space-x-2">
      {visible.map((p) => (
        <PersonAvatar key={p.id} person={p} size={size} ring />
      ))}
      {overflow > 0 && (
        <span
          className="inline-flex items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground ring-2 ring-background"
          style={{ width: size, height: size }}
        >
          +{overflow}
        </span>
      )}
    </div>
  );
}
