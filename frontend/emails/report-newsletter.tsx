import { Body, Container, Head, Html, Preview } from "@react-email/components";
import { BalancesSection, type BalanceItem } from "./components/report/BalancesSection";
import { ReportFooter } from "./components/report/ReportFooter";
import { ReportHeader } from "./components/report/ReportHeader";
import { TransactionsSection, type TransactionItem } from "./components/report/TransactionsSection";

export type ReportNewsletterProps = {
  reportName: string;
  generatedAt: string;
  accounts: BalanceItem[];
  transactionsModeLabel: string;
  transactions: TransactionItem[];
  manageUrl: string;
};

export default function ReportNewsletter({
  reportName,
  generatedAt,
  accounts,
  transactionsModeLabel,
  transactions,
  manageUrl,
}: ReportNewsletterProps) {
  return (
    <Html>
      <Head />
      <Preview>{reportName} — your latest financial summary</Preview>
      <Body style={{ backgroundColor: "#F3F4F6", margin: 0, fontFamily: "-apple-system, Segoe UI, sans-serif" }}>
        <Container style={{ maxWidth: "600px", width: "100%", margin: "0 auto", backgroundColor: "#FFFFFF" }}>
          <ReportHeader reportName={reportName} generatedAt={generatedAt} />
          <BalancesSection accounts={accounts} />
          <TransactionsSection modeLabel={transactionsModeLabel} items={transactions} />
          <ReportFooter manageUrl={manageUrl} sentAt={generatedAt} />
        </Container>
      </Body>
    </Html>
  );
}
