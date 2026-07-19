import { Hr, Link, Section, Text } from "@react-email/components";

export function ReportFooter({ manageUrl, sentAt }: { manageUrl: string; sentAt: string }) {
  const formatted = new Date(sentAt).toLocaleString("en-US");
  return (
    <Section style={{ padding: "16px 20px 24px" }}>
      <Hr style={{ borderColor: "#E5E7EB" }} />
      <Text style={{ fontSize: "11px", color: "#9CA3AF", margin: "12px 0 0" }}>
        Sent {formatted} · <Link href={manageUrl} style={{ color: "#6B7280" }}>Manage this report</Link>
      </Text>
    </Section>
  );
}
