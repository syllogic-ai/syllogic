"use client";
import { useRouter } from "next/navigation";
import {
  RiAddLine,
  RiLineChartLine,
  RiLinksLine,
  RiPencilLine,
} from "@remixicon/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function InvestmentsEmpty() {
  const router = useRouter();
  const go = () => router.push("/investments/connect");
  return (
    <div className="flex-1 flex items-center justify-center p-10">
      <div className="max-w-xl w-full flex flex-col">
        <Card className="rounded-none">
          <CardContent className="px-8 pt-8 pb-6 flex flex-col items-center text-center gap-3">
            <div className="w-11 h-11 border border-border flex items-center justify-center bg-muted/40">
              <RiLineChartLine size={20} className="text-muted-foreground" />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-base font-semibold">No holdings yet</div>
              <div className="text-xs text-muted-foreground leading-relaxed max-w-[340px]">
                Track your portfolio by connecting a broker for automatic sync,
                or add holdings manually.
              </div>
            </div>
          </CardContent>
        </Card>
        <div className="grid grid-cols-2 border border-t-0 border-border">
          <div className="p-6 flex flex-col gap-3 border-r border-border">
            <div className="flex items-center gap-2">
              <RiLinksLine size={16} />
              <span className="font-semibold text-sm">Connect broker</span>
              <Badge className="ml-auto text-[9px] tracking-wider rounded-none">
                RECOMMENDED
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground leading-relaxed">
              Connect Interactive Brokers via Flex Query. Positions and trades
              sync automatically.
            </div>
            <ul className="mt-1 pl-4 list-disc space-y-1">
              {[
                "Automatic position sync",
                "Trade history imported",
                "No manual entry needed",
              ].map((t) => (
                <li key={t} className="text-xs text-muted-foreground">
                  {t}
                </li>
              ))}
            </ul>
            <Button onClick={go} className="mt-1 w-full">
              <RiLinksLine size={13} /> Connect IBKR
            </Button>
          </div>
          <div className="p-6 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <RiPencilLine size={16} />
              <span className="font-semibold text-sm">Add manually</span>
            </div>
            <div className="text-xs text-muted-foreground leading-relaxed">
              Create an account, search by symbol, and enter quantities. Prices
              are fetched automatically.
            </div>
            <ul className="mt-1 pl-4 list-disc space-y-1">
              {[
                "No broker needed",
                "Prices updated daily",
                "You manage quantities",
              ].map((t) => (
                <li key={t} className="text-xs text-muted-foreground">
                  {t}
                </li>
              ))}
            </ul>
            <Button onClick={go} variant="outline" className="mt-1 w-full">
              <RiAddLine size={13} /> Add holding
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
