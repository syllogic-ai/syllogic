import { Heading, Section, Text } from "@react-email/components";

export function ReportHeader({ reportName, generatedAt }: { reportName: string; generatedAt: string }) {
  const formatted = new Date(generatedAt).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  return (
    <Section style={{ padding: "24px 20px 8px" }}>
      <Heading as="h1" style={{ fontSize: "20px", margin: 0, color: "#111827" }}>
        {reportName}
      </Heading>
      <Text style={{ fontSize: "13px", color: "#6B7280", margin: "4px 0 0" }}>{formatted}</Text>
    </Section>
  );
}
