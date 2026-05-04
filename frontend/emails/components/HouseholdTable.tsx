import { Section, Text } from "@react-email/components";

type Person = {
  personId: string;
  name: string;
  cash: number;
  investments: number;
  properties: number;
  vehicles: number;
  total: number;
};

const fmt = (n: number) =>
  n.toLocaleString("en-EU", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

export function HouseholdTable({ people }: { people: Person[] }) {
  return (
    <Section style={{ marginBottom: "16px" }}>
      <Text style={{ fontSize: "16px", fontWeight: 600 }}>Household snapshot</Text>
      <table cellPadding={6} style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
            <th>Person</th>
            <th>Cash</th>
            <th>Investments</th>
            <th>Properties</th>
            <th>Vehicles</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {people.map((p) => (
            <tr key={p.personId} style={{ borderBottom: "1px solid #eee" }}>
              <td>{p.name}</td>
              <td>{fmt(p.cash)}</td>
              <td>{fmt(p.investments)}</td>
              <td>{fmt(p.properties)}</td>
              <td>{fmt(p.vehicles)}</td>
              <td>
                <strong>{fmt(p.total)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}
