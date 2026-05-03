"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PersonForm, type PersonFormValues } from "./person-form";
import { PersonAvatar } from "./person-avatar";

type Person = {
  id: string;
  name: string;
  kind: string;
  color?: string | null;
  avatarUrl?: string | null;
};

function buildFormData(values: PersonFormValues): FormData {
  const fd = new FormData();
  fd.set("name", values.name);
  fd.set("color", values.color);
  if (values.avatar) fd.set("avatar", values.avatar);
  if (values.clearAvatar) fd.set("clearAvatar", "1");
  return fd;
}

export function PeopleList(props: { initialPeople: Person[] }) {
  const [people, setPeople] = useState(props.initialPeople);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  async function refresh() {
    const r = await fetch("/api/people");
    const j = await r.json();
    setPeople(j.people);
  }

  async function create(values: PersonFormValues) {
    await fetch("/api/people", { method: "POST", body: buildFormData(values) });
    await refresh();
    setAdding(false);
  }

  async function update(id: string, values: PersonFormValues) {
    await fetch(`/api/people/${id}`, { method: "PATCH", body: buildFormData(values) });
    await refresh();
    setEditingId(null);
  }

  async function remove(id: string) {
    const r = await fetch(`/api/people/${id}`, { method: "DELETE" });
    if (r.status === 409) {
      const j = await r.json();
      alert(
        `Cannot delete: this person is the sole owner of ${j.blockers.length} item(s). Reassign first.`
      );
      return;
    }
    await refresh();
  }

  return (
    <div className="space-y-4">
      <ul className="divide-y rounded-md border">
        {people.map((p) => (
          <li key={p.id} className="flex items-center gap-3 p-3">
            <PersonAvatar person={p} size={36} />
            <span className="flex-1 font-medium">{p.name}</span>
            {p.kind === "self" && (
              <span className="text-xs text-muted-foreground">you</span>
            )}
            <Button variant="ghost" size="sm" onClick={() => setEditingId(p.id)}>
              Edit
            </Button>
            {p.kind !== "self" && (
              <Button variant="ghost" size="sm" onClick={() => remove(p.id)}>
                Delete
              </Button>
            )}
          </li>
        ))}
      </ul>

      {editingId && (
        <div className="rounded-md border p-4">
          <h2 className="mb-3 font-medium">
            Edit {people.find((p) => p.id === editingId)?.name}
          </h2>
          <PersonForm
            initial={{
              name: people.find((p) => p.id === editingId)!.name,
              color: people.find((p) => p.id === editingId)!.color ?? undefined,
              avatarUrl: people.find((p) => p.id === editingId)!.avatarUrl ?? undefined,
            }}
            submitLabel="Save"
            onSubmit={(v) => update(editingId, v)}
            onCancel={() => setEditingId(null)}
          />
        </div>
      )}

      {adding ? (
        <div className="rounded-md border p-4">
          <h2 className="mb-3 font-medium">Add person</h2>
          <PersonForm
            submitLabel="Add person"
            onSubmit={create}
            onCancel={() => setAdding(false)}
          />
        </div>
      ) : (
        <Button variant="outline" onClick={() => setAdding(true)}>
          Add person
        </Button>
      )}
    </div>
  );
}
