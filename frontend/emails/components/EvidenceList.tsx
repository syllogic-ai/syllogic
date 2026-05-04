import { Section, Text, Link } from "@react-email/components";

type Item = { source: string; url: string; quote: string; relevance: string };

function isSafeUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export function EvidenceList({ items }: { items: Item[] }) {
  if (items.length === 0) return null;
  return (
    <Section style={{ marginBottom: "16px" }}>
      <Text style={{ fontSize: "16px", fontWeight: 600 }}>Evidence</Text>
      <ol style={{ paddingLeft: "20px", margin: 0 }}>
        {items.map((it, i) => (
          <li key={i} style={{ marginBottom: "12px", fontSize: "14px" }}>
            <Link href={isSafeUrl(it.url) ? it.url : "#"}>
              <strong>{it.source}</strong>
            </Link>
            <div style={{ color: "#555", fontStyle: "italic" }}>&ldquo;{it.quote}&rdquo;</div>
            <div style={{ color: "#888" }}>{it.relevance}</div>
          </li>
        ))}
      </ol>
    </Section>
  );
}
