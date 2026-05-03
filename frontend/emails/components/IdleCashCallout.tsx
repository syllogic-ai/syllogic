import { Section, Text } from "@react-email/components";

export function IdleCashCallout({ nudge }: { nudge: string }) {
  return (
    <Section
      style={{
        background: "#fef3c7",
        padding: "12px 16px",
        borderRadius: "6px",
        marginBottom: "16px",
      }}
    >
      <Text style={{ margin: 0, fontWeight: 500 }}>Idle cash</Text>
      <Text style={{ margin: "4px 0 0 0", fontSize: "14px" }}>{nudge}</Text>
    </Section>
  );
}
