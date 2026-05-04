import { Body, Container, Head, Html, Preview, Section, Text } from "@react-email/components";
import type { RoutineOutput } from "@/lib/routines/schema";
import { StatusBanner } from "./components/StatusBanner";
import { HouseholdTable } from "./components/HouseholdTable";
import { EvidenceList } from "./components/EvidenceList";
import { NewsCard } from "./components/NewsCard";
import { RecommendationItems } from "./components/RecommendationItem";

export function Digest({ output, runUrl }: { output: RoutineOutput; runUrl?: string }) {
  return (
    <Html>
      <Head />
      <Preview>{output.headline}</Preview>
      <Body style={{ background: "#f5f5f5", fontFamily: "-apple-system,BlinkMacSystemFont,sans-serif" }}>
        <Container style={{ background: "#fff", maxWidth: 640, margin: "0 auto", padding: "24px" }}>
          <StatusBanner status={output.status} headline={output.headline} />
          <Section style={{ marginBottom: "16px" }}>
            <Text style={{ fontSize: "14px", color: "#444", lineHeight: "1.5" }}>{output.summary}</Text>
          </Section>
          <HouseholdTable people={output.household.people} />
          {output.positions.length > 0 && (
            <Section style={{ marginBottom: "16px" }}>
              <Text style={{ fontSize: "16px", fontWeight: 600 }}>Positions vs. target</Text>
              <table
                cellPadding={6}
                style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}
              >
                <thead>
                  <tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
                    <th>Sleeve</th>
                    <th>Current</th>
                    <th>Target</th>
                    <th>&Delta;</th>
                  </tr>
                </thead>
                <tbody>
                  {output.positions.map((p, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                      <td>{p.label}</td>
                      <td>{p.current.toLocaleString()}</td>
                      <td>{p.target != null ? p.target.toLocaleString() : "—"}</td>
                      <td>{p.deltaPct != null ? `${p.deltaPct.toFixed(1)}%` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
          <RecommendationItems items={output.recommendations} />
          <NewsCard items={output.news} />
          <EvidenceList items={output.evidence} />
          {runUrl !== undefined && (
            <Section style={{ marginTop: "24px", borderTop: "1px solid #ddd", paddingTop: "12px" }}>
              <Text style={{ fontSize: "12px", color: "#888" }}>
                <a href={runUrl}>View this run online</a> &middot; Research and analysis only, not
                financial advice.
              </Text>
            </Section>
          )}
        </Container>
      </Body>
    </Html>
  );
}
