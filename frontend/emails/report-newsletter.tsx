import { Body, Container, Head, Html, Preview, Section } from "@react-email/components";
import { BalancesSection, type BalanceItem } from "./components/report/BalancesSection";
import { ReportFooter } from "./components/report/ReportFooter";
import { ReportHeader } from "./components/report/ReportHeader";
import { TotalBalance } from "./components/report/TotalBalance";
import { TransactionsSection, type TransactionItem } from "./components/report/TransactionsSection";
import { dark, fontStack, light } from "./components/report/tokens";

export type ReportNewsletterProps = {
  reportName: string;
  generatedAt: string;
  periodLabel: string;
  totalBalance: string | null;
  totalCurrency: string;
  accounts: BalanceItem[];
  transactionsModeLabel: string;
  transactions: TransactionItem[];
  manageUrl: string;
};

/**
 * Dark mode is opt-in per client. Gmail and most Outlook builds ignore
 * prefers-color-scheme entirely and render the light palette, which is why
 * light is the baseline rather than a fallback.
 *
 * The backdrop rule targets the table wrapper as well as <body>: several
 * clients drop the body background while honouring table cell backgrounds.
 */
const darkModeCss = `
  :root { color-scheme: light dark; supported-color-schemes: light dark; }
  @media (prefers-color-scheme: dark) {
    .sy-body,
    .sy-page,
    .sy-page > tbody > tr > td { background-color: ${dark.background} !important; }
    .sy-card   { background-color: ${dark.card} !important; border-color: ${dark.border} !important; }
    .sy-fg     { color: ${dark.foreground} !important; }
    .sy-muted  { color: ${dark.mutedForeground} !important; }
    .sy-rule   { border-color: ${dark.border} !important; }
    .sy-chip   { background-color: ${dark.muted} !important; }
    .sy-out    { color: ${dark.destructive} !important; }
    .sy-logo   { background-color: ${dark.muted} !important; }
  }
`;

export default function ReportNewsletter({
  reportName,
  generatedAt,
  periodLabel,
  totalBalance,
  totalCurrency,
  accounts,
  transactionsModeLabel,
  transactions,
  manageUrl,
}: ReportNewsletterProps) {
  return (
    <Html>
      <Head>
        <style dangerouslySetInnerHTML={{ __html: darkModeCss }} />
      </Head>
      <Preview>{`${reportName} — ${periodLabel}`}</Preview>
      <Body
        className="sy-body"
        style={{ backgroundColor: light.secondary, margin: 0, padding: 0, fontFamily: fontStack }}
      >
        <Section className="sy-page" style={{ backgroundColor: light.secondary, width: "100%", padding: "24px 0" }}>
          <Container
            className="sy-card"
            style={{
              maxWidth: "600px",
              width: "100%",
              margin: "0 auto",
              backgroundColor: light.background,
              border: `1px solid ${light.border}`,
            }}
          >
            <ReportHeader reportName={reportName} periodLabel={periodLabel} generatedAt={generatedAt} />
            <TotalBalance amount={totalBalance} currency={totalCurrency} />
            <BalancesSection accounts={accounts} />
            <TransactionsSection modeLabel={transactionsModeLabel} items={transactions} />
            <ReportFooter manageUrl={manageUrl} sentAt={generatedAt} />
          </Container>
        </Section>
      </Body>
    </Html>
  );
}
