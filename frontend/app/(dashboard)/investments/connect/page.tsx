import { ConnectIBKRForm } from "@/components/investments/ConnectIBKRForm";
import { AddManualHoldingForm } from "@/components/investments/AddManualHoldingForm";

export default function ConnectPage() {
  return (
    <div className="p-6 grid gap-8 md:grid-cols-2">
      <section>
        <h2 className="font-semibold mb-3">Connect Interactive Brokers</h2>
        <ConnectIBKRForm />
      </section>
      <section>
        <h2 className="font-semibold mb-3">Add a manual holding</h2>
        <AddManualHoldingForm />
      </section>
    </div>
  );
}
