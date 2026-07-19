import { render } from "@react-email/render";
import ReportNewsletter, { type ReportNewsletterProps } from "./report-newsletter";

async function main() {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  const input = JSON.parse(Buffer.concat(chunks).toString("utf-8"));

  const props: ReportNewsletterProps = {
    reportName: input.report_name,
    generatedAt: input.generated_at,
    accounts: input.accounts,
    transactionsModeLabel: input.transactions.mode_label,
    transactions: input.transactions.items,
    manageUrl: input.manage_url ?? "#",
  };

  const element = ReportNewsletter(props);
  const html = await render(element, { pretty: false });
  const text = await render(element, { plainText: true });

  process.stdout.write(JSON.stringify({ html, text }));
}

main().catch((err) => {
  process.stderr.write(String(err?.stack ?? err));
  process.exit(1);
});
