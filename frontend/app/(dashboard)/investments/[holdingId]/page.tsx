import { getHoldingHistory } from "@/lib/api/investments";

export const dynamic = "force-dynamic";

export default async function HoldingDetailPage({
  params,
}: {
  params: Promise<{ holdingId: string }>;
}) {
  const { holdingId } = await params;
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const oneYearAgo = new Date(now.getTime() - 365 * 86400e3)
    .toISOString()
    .slice(0, 10);
  const history = await getHoldingHistory(holdingId, oneYearAgo, today);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">Holding history</h1>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th>Date</th>
            <th className="text-right">Value</th>
          </tr>
        </thead>
        <tbody>
          {history.map((p) => (
            <tr key={p.date} className="border-t">
              <td className="py-1">{p.date}</td>
              <td className="text-right">{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
