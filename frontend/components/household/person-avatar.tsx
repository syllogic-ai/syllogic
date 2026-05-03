import Image from "next/image";

type Person = {
  id: string;
  name: string;
  color?: string | null;
  avatarUrl?: string | null;
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

export function PersonAvatar({
  person,
  size = 32,
  ring = false,
}: {
  person: Person;
  size?: number;
  ring?: boolean;
}) {
  const px = `${size}px`;
  const ringCls = ring ? "ring-2 ring-background" : "";
  if (person.avatarUrl) {
    return (
      <Image
        src={person.avatarUrl}
        alt={person.name}
        width={size}
        height={size}
        className={`rounded-full object-cover ${ringCls}`}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    <span
      title={person.name}
      className={`inline-flex items-center justify-center rounded-full text-white font-medium ${ringCls}`}
      style={{
        background: person.color ?? "#6B7280",
        width: px,
        height: px,
        fontSize: Math.max(10, Math.floor(size * 0.4)),
      }}
    >
      {initials(person.name)}
    </span>
  );
}
