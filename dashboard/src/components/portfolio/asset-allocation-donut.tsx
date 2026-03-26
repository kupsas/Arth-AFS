/**
 * asset-allocation-donut.tsx — single donut by asset class (rupee values from B3
 * asset_class_breakdown). Replaces the older multi-tab asset-allocation card.
 */

"use client";

import * as React from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolioSummary } from "@/hooks/use-portfolio";
import { prettyAssetClassLabel } from "@/lib/holdings-display";
import { formatCurrency, formatPercent } from "@/lib/utils";

const COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export interface AssetAllocationDonutProps {
  userId: string;
}

export function AssetAllocationDonut({ userId }: AssetAllocationDonutProps) {
  const { data, isLoading } = usePortfolioSummary({ user_id: userId });
  const breakdown = data?.asset_class_breakdown;

  const pieData = React.useMemo(() => {
    if (!breakdown) return [];
    const total = Object.values(breakdown).reduce(
      (s, row) => s + (row.current_value ?? 0),
      0,
    );
    if (total <= 0) return [];
    return Object.entries(breakdown)
      .map(([key, row]) => ({
        name: prettyAssetClassLabel(key),
        rawKey: key,
        value: row.current_value,
        pct: (100 * row.current_value) / total,
      }))
      .filter((d) => d.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [breakdown]);

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Asset allocation</CardTitle>
        <p className="text-xs text-muted-foreground">
          Share of portfolio by asset class (current value)
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="mx-auto aspect-square max-h-[240px] w-full max-w-[240px] rounded-full" />
        ) : pieData.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No allocation data yet.
          </p>
        ) : (
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={52}
                  outerRadius={80}
                  paddingAngle={1}
                >
                  {pieData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={COLORS[i % COLORS.length]}
                      stroke="transparent"
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, _n, item) => {
                    const row = item?.payload as { pct?: number };
                    const p =
                      row?.pct != null ? formatPercent(row.pct, 1) : "";
                    return [`${formatCurrency(value)} (${p})`, "Value"];
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
