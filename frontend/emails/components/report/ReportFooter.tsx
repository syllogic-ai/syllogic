import { Hr, Link, Section, Text } from "@react-email/components";
import { light } from "./tokens";

export function ReportFooter({ manageUrl, sentAt }: { manageUrl: string; sentAt: string }) {
  const formatted = new Date(sentAt).toLocaleString("en-GB");
  return (
    <Section style={{ padding: "24px 28px 28px" }}>
      <Hr className="sy-rule" style={{ borderColor: light.border, margin: "0 0 14px" }} />
      <Text className="sy-muted" style={{ fontSize: "11px", color: light.mutedForeground, margin: 0, lineHeight: 1.6 }}>
        Sent {formatted} ·{" "}
        <Link href={manageUrl} className="sy-fg" style={{ color: light.foreground, textDecoration: "underline" }}>
          Manage this report
        </Link>
      </Text>
    </Section>
  );
}
