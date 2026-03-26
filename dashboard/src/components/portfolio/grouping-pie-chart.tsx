/**
 * grouping-pie-chart.tsx — donut that splits a sleeve (e.g. equities) by a
 * grouping dimension. Values are rupees; segment labels show ₹ + % of total.
 */

"use client";

import * as React from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, formatPercent } from "@/lib/utils";

const SLICE_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export interface GroupingPieSlice {
  name: string;
  value: number;
}

export interface GroupingPieChartProps {
  title: string;
  description?: string;
  data: GroupingPieSlice[];
  isLoading?: boolean;
  emptyMessage?: string;
}

export function GroupingPieChart({
  title,
  description,
  data,
  isLoading,
  emptyMessage = "Nothing to chart for this grouping.",
}: GroupingPieChartProps) {
  const total = React.useMemo(
    () => data.reduce((s, d) => s + d.value, 0),
    [data],
  );

  const pieData = React.useMemo(() => {
    if (total <= 0) return [];
    return data
      .filter((d) => d.value > 0)
      .map((d) => ({
        ...d,
        pct: (100 * d.value) / total,
      }))
      .sort((a, b) => b.value - a.value);
  }, [data, total]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="mx-auto aspect-square max-h-[260px] w-full max-w-[260px] rounded-full" />
        ) : pieData.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            {emptyMessage}
          </p>
        ) : (
          <div className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={58}
                  outerRadius={88}
                  paddingAngle={1}
                >
                  {pieData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={SLICE_COLORS[i % SLICE_COLORS.length]}
                      stroke="transparent"
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, _name, item) => {
                    const row = item?.payload as {
                      pct?: number;
                    };
                    const pct =
                      row?.pct != null ? formatPercent(row.pct, 1) : "";
                    return [`${formatCurrency(value)} (${pct})`, "Value"];
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
