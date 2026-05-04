"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PersonAvatar } from "@/components/household/person-avatar";

type Person = { id: string; name: string; color?: string | null; avatarUrl?: string | null };

export function PersonFilter(props: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [people, setPeople] = useState<Person[]>([]);

  useEffect(() => {
    fetch("/api/people")
      .then((r) => r.json())
      .then((j) => setPeople(j.people ?? []));
  }, []);

  if (people.length < 2) return null; // single-person households: hide.

  function toggle(id: string) {
    props.onChange(
      props.value.includes(id) ? props.value.filter((x) => x !== id) : [...props.value, id]
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-sm text-muted-foreground">View:</span>
      <Button
        size="sm"
        variant={props.value.length === 0 ? "default" : "outline"}
        onClick={() => props.onChange([])}
      >
        All
      </Button>
      {people.map((p) => (
        <Button
          key={p.id}
          size="sm"
          variant={props.value.includes(p.id) ? "default" : "outline"}
          onClick={() => toggle(p.id)}
        >
          <span className="mr-2">
            <PersonAvatar person={p} size={18} />
          </span>
          {p.name}
        </Button>
      ))}
    </div>
  );
}
