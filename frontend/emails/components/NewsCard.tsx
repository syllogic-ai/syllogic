import { Section, Text, Link } from "@react-email/components";

type Item = { title: string; source: string; url: string; dateIso: string; summary: string };

export function NewsCard({ items }: { items: Item[] }) {
  if (items.length === 0) return null;
  return (
    <Section style={{ marginBottom: "16px" }}>
      <Text style={{ fontSize: "16px", fontWeight: 600 }}>This week&apos;s signals</Text>
      {items.map((n, i) => (
        <div key={i} style={{ borderLeft: "3px solid #ddd", padding: "8px 12px", marginBottom: "8px" }}>
          <Link href={n.url} style={{ fontSize: "15px", fontWeight: 500 }}>
            {n.title}
          </Link>
          <div style={{ color: "#888", fontSize: "12px" }}>
            {n.source} &middot; {new Date(n.dateIso).toLocaleDateString()}
          </div>
          <div style={{ fontSize: "14px", marginTop: "4px" }}>{n.summary}</div>
        </div>
      ))}
    </Section>
  );
}
