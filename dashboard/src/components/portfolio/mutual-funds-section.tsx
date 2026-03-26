/**
 * mutual-funds-section.tsx — F3: MF header, grouping, pie, table + batch XIRR.
 */

"use client";

import * as React from "react";

import { GroupingPieChart } from "@/components/portfolio/grouping-pie-chart";
import { GroupingToggle } from "@/components/portfolio/grouping-toggle";
import {
  buildMfGroups,
  MfHoldingsTable,
  type MfGroupMode,
} from "@/components/portfolio/mf-holdings-table";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useBatchReturns,
  useHoldings,
  usePortfolioSummary,
} from "@/hooks/use-portfolio";
import type { Holding } from "@/lib/types";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

export interface MutualFundsSectionProps {
  userId: string;
}

type HoldingRow = Holding & { id: number };

const MF_GROUP_OPTIONS: { value: MfGroupMode; label: string }[] = [
  { value: "fund_category", label: "Fund category" },
  { value: "fund_house", label: "Fund house" },
];

function gainClass(v: number | null | undefined) {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-red-600 dark:text-red-400";
  return "text-muted-foreground";
}

export function MutualFundsSection({ userId }: MutualFundsSectionProps) {
  const [groupMode, setGroupMode] = React.useState<MfGroupMode>("fund_category");
  const { data: holdings, isLoading } = useHoldings({
    user_id: userId,
    asset_class: "MUTUAL_FUND",
    is_active: true,
  });
  const { data: summary, isLoading: sLoad } = usePortfolioSummary({
    user_id: userId,
  });
  const { data: batchRet, isLoading: rLoad } = useBatchReturns({
    user_id: userId,
  });

  const rows = React.useMemo(
    () => (holdings ?? []).filter((h): h is HoldingRow => h.id != null),
    [holdings],
  );

  const mf = summary?.asset_class_breakdown?.MUTUAL_FUND;

  const returnsMap = batchRet?.returns ?? {};

  const pieData = React.useMemo(() => {
    const blocks = buildMfGroups(rows, groupMode);
    return blocks.map((b) => ({ name: b.key, value: b.sumValue }));
  }, [rows, groupMode]);

  if (!isLoading && rows.length === 0) {
    return null;
  }

  return (
    <section
      id="holdings-section-mf"
      className="scroll-mt-24 space-y-4"
      aria-label="Mutual funds"
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Mutual funds</CardTitle>
          <CardDescription>
            {sLoad ? (
              <Skeleton className="h-4 w-72" />
            ) : (
              <>
                <span className="text-foreground font-semibold text-base">
                  {formatCurrency(mf?.current_value ?? 0)}
                </span>
                {mf?.overall_gain != null && mf.overall_gain_pct != null ? (
                  <span
                    className={cn(
                      "ml-2 text-sm font-medium",
                      gainClass(mf.overall_gain),
                    )}
                  >
                    {mf.overall_gain > 0 ? "+" : ""}
                    {formatCurrency(mf.overall_gain)} (
                    {mf.overall_gain_pct > 0 ? "+" : ""}
                    {formatPercent(mf.overall_gain_pct, 1)}) overall
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
        options={MF_GROUP_OPTIONS}
        value={groupMode}
        onChange={setGroupMode}
      />

      <GroupingPieChart
        title="Mutual fund mix"
        description="By selected grouping"
        data={pieData}
        isLoading={isLoading}
      />

      {isLoading || rLoad ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <MfHoldingsTable
          holdings={rows}
          groupMode={groupMode}
          returnsByHoldingId={returnsMap}
        />
      )}
    </section>
  );
}
