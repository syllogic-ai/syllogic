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

type CacheEntry<T> = { value: T; timestamp: number };
const TTL_MS = 30_000;

const peopleCache: { entry?: CacheEntry<Person[]> } = {};
const ownersCache = new Map<string, CacheEntry<{ personId: string; share: number | null }[]>>();

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

async function loadOwners(entityType: EntityType, entityId: string) {
  const key = `${entityType}:${entityId}`;
  const existing = ownersCache.get(key);
  if (isFresh(existing)) return existing.value;
  try {
    const r = await fetch(`/api/owners/${entityType}/${entityId}`);
    if (!r.ok) return [];
    const j = await r.json();
    const owners = Array.isArray(j?.owners) ? j.owners : [];
    ownersCache.set(key, { value: owners, timestamp: Date.now() });
    return owners;
  } catch {
    return [];
  }
}

/**
 * Renders a stacked-avatar row of the people who own this entity.
 * Hidden in single-person households (only one person total).
 */
export function OwnerBadges({
  entityType,
  entityId,
  size = 24,
  max = 3,
}: {
  entityType: EntityType;
  entityId: string;
  size?: number;
  max?: number;
}) {
  const [people, setPeople] = useState<Person[]>([]);
  const [ownerIds, setOwnerIds] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadPeople(), loadOwners(entityType, entityId)]).then(
      ([all, owners]) => {
        if (cancelled) return;
        setPeople(all);
        setOwnerIds(owners.map((o: { personId: string }) => o.personId));
      }
    );
    return () => {
      cancelled = true;
    };
  }, [entityType, entityId]);

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
