/**
 * equities-section.tsx — F2: header, grouping, donut, best/drags, equity table.
 */

"use client";

import * as React from "react";

import { BestGainsDrags } from "@/components/portfolio/best-gains-drags";
import {
  buildEquityGroups,
  EquityHoldingsTable,
  type EquityGroupMode,
} from "@/components/portfolio/equity-holdings-table";
import { GroupingPieChart } from "@/components/portfolio/grouping-pie-chart";
import { GroupingToggle } from "@/components/portfolio/grouping-toggle";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHoldings, usePortfolioSummary } from "@/hooks/use-portfolio";
import type { Holding } from "@/lib/types";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

export interface EquitiesSectionProps {
  userId: string;
}

type HoldingRow = Holding & { id: number };

const EQUITY_GROUP_OPTIONS: {
  value: EquityGroupMode;
  label: string;
}[] = [
  { value: "sector", label: "Sector" },
  { value: "market_cap", label: "Market cap" },
  { value: "holding_period", label: "Holding period" },
];

function gainClass(v: number | null | undefined) {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-red-600 dark:text-red-400";
  return "text-muted-foreground";
}

export function EquitiesSection({ userId }: EquitiesSectionProps) {
  const [groupMode, setGroupMode] = React.useState<EquityGroupMode>("sector");
  const { data: holdings, isLoading } = useHoldings({
    user_id: userId,
    asset_class: "EQUITY",
    is_active: true,
  });
  const { data: summary, isLoading: sLoad } = usePortfolioSummary({
    user_id: userId,
  });

  const rows = React.useMemo(
    () => (holdings ?? []).filter((h): h is HoldingRow => h.id != null),
    [holdings],
  );

  const eq = summary?.asset_class_breakdown?.EQUITY;

  const pieData = React.useMemo(() => {
    const blocks = buildEquityGroups(rows, groupMode);
    return blocks.map((b) => ({ name: b.key, value: b.sumValue }));
  }, [rows, groupMode]);

  if (!isLoading && rows.length === 0) {
    return null;
  }

  const hint =
    groupMode === "holding_period"
      ? "LTCG-style buckets are not in the data model yet — everything sits in one group for now."
      : undefined;

  return (
    <section
      id="holdings-section-equity"
      className="scroll-mt-24 space-y-4"
      aria-label="Equities"
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Equities</CardTitle>
          <CardDescription>
            {sLoad ? (
              <Skeleton className="h-4 w-72" />
            ) : (
              <>
                <span className="text-foreground font-semibold text-base">
                  {formatCurrency(eq?.current_value ?? 0)}
                </span>
                {eq?.overall_gain != null && eq.overall_gain_pct != null ? (
                  <span
                    className={cn(
                      "ml-2 text-sm font-medium",
                      gainClass(eq.overall_gain),
                    )}
                  >
                    {eq.overall_gain > 0 ? "+" : ""}
                    {formatCurrency(eq.overall_gain)} (
                    {eq.overall_gain_pct > 0 ? "+" : ""}
                    {formatPercent(eq.overall_gain_pct, 1)}) overall
                  </span>
                ) : (
                  <span className="ml-2 text-sm text-muted-foreground">
                    Sub-portfolio gain needs cost on each row.
                  </span>
                )}
              </>
            )}
          </CardDescription>
        </CardHeader>
      </Card>

      <GroupingToggle
        options={EQUITY_GROUP_OPTIONS}
        value={groupMode}
        onChange={setGroupMode}
        hint={hint}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <GroupingPieChart
          title="Equity mix"
          description="By selected grouping"
          data={pieData}
          isLoading={isLoading}
        />
        <div className="min-h-[120px]">
          {isLoading ? (
            <Skeleton className="h-full min-h-[120px] w-full" />
          ) : (
            <BestGainsDrags holdings={rows} />
          )}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <EquityHoldingsTable holdings={rows} groupMode={groupMode} />
      )}
    </section>
  );
}
