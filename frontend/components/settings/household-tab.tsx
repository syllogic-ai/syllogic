import { PeopleList } from "@/components/household/people-list";

type Person = {
  id: string;
  name: string;
  kind: string;
  color?: string | null;
  avatarUrl?: string | null;
};

export function HouseholdTab({ people }: { people: Person[] }) {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Your household</h2>
        <p className="text-sm text-muted-foreground">
          Track who owns what — useful for joint accounts and household-level reports.
        </p>
      </div>
      <PeopleList initialPeople={people} />
    </div>
  );
}
