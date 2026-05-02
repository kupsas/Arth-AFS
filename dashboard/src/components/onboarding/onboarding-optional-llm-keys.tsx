"use client";

/**
 * Optional LLM API keys during onboarding (Track 2 Phase 3c).
 *
 * Copy: one indicative accuracy pair (rules vs cloud), brief cost per 1k framing.
 * Maintainers: `dashboard/src/data/classification-llm-education.ts`.
 *
 * Keys → encrypted ``UserSecrets``. Skipping keys = rules-only for gaps (supported).
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ONBOARDING_INDICATIVE_CLOUD_ROWS_PER_1000,
  ONBOARDING_INDICATIVE_OVERALL_PCT,
  ONBOARDING_PRIMARY_COST_USD_PER_100,
  costUsdForCloudRowCount,
  formatUsd,
} from "@/data/classification-llm-education";
import { buildApiUrl } from "@/lib/api-base";
import {
  getUserFacingErrorMessage,
  userMessageFromApiResponseBody,
} from "@/lib/user-facing-api-error";

async function postKeys(body: {
  openai_api_key?: string | null;
  anthropic_api_key?: string | null;
  google_api_key?: string | null;
}): Promise<void> {
  const res = await fetch(buildApiUrl("/api/onboarding/api-key"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const t = await res.text();
  if (!res.ok) {
    throw new Error(
      userMessageFromApiResponseBody(t) || "Could not save keys. Try again.",
    );
  }
}

export function OnboardingOptionalLlmKeys() {
  const [openai, setOpenai] = React.useState("");
  const [anthropic, setAnthropic] = React.useState("");
  const [google, setGoogle] = React.useState("");
  const [msg, setMsg] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function onSave() {
    setMsg(null);
    setErr(null);
    setBusy(true);
    try {
      await postKeys({
        openai_api_key: openai || null,
        anthropic_api_key: anthropic || null,
        google_api_key: google || null,
      });
      setMsg(
        "Saved — keys are encrypted at rest. Clear a field and save again to remove a key.",
      );
    } catch (e) {
      setErr(getUserFacingErrorMessage(e) || "Could not save keys. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const acc = ONBOARDING_INDICATIVE_OVERALL_PCT;
  const cloudRowsPer1k = ONBOARDING_INDICATIVE_CLOUD_ROWS_PER_1000;
  /** $ for classifying exactly `cloudRowsPer1k` cloud rows, from benchmark “$/100 similar rows”. */
  const costForCloudSlice = costUsdForCloudRowCount(
    cloudRowsPer1k,
    ONBOARDING_PRIMARY_COST_USD_PER_100,
  );

  return (
    <Card className="mx-auto w-full max-w-2xl">
      <CardHeader className="space-y-2">
        <CardTitle>Optional: smarter auto-labels</CardTitle>
        <CardDescription>
          Add an API key if you want cloud help labeling messy bank text. Skip to stay fully local
          (more manual fixes later).
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        <div className="space-y-3 text-sm text-muted-foreground leading-relaxed">
          <p>
            When you continue, Arth will fetch bank alert emails and parse transactions.{" "}
            Every classification starts with a{" "}
            <strong className="text-foreground">local rules engine</strong>. If you add an API key below,
            only rows that still need help may be sent to a cloud model; if you skip keys, we never
            call an external model for this step.
          </p>
          <p>
            <strong className="text-foreground">Without a cloud key,</strong> we never call an
            external model: you still get an automatic first pass, but you&apos;ll spend more time in
            the review step fixing labels.

            <strong className="text-foreground">With a key,</strong> a small cloud model fills the
            fuzzy bits (weird merchant text, edge cases). Same pipeline — the difference is how much
            automation you get before you touch the rows yourself.
          </p>
          <p>
            <strong className="text-foreground">Overall classification quality (indicative):</strong>{" "}
            think <strong className="text-foreground">~{acc.rulesOnly}%</strong> of labels looking right
            without any cloud help vs <strong className="text-foreground">~{acc.withCloudModel}%</strong>{" "}
            when the cloud step runs.
          </p>
          <p>
            <strong className="text-foreground">Cost (indicative):</strong> expect on the order of{" "}
            <strong className="text-foreground">~{cloudRowsPer1k}</strong> cloud-classified rows per{" "}
            <strong className="text-foreground">1,000</strong> transactions; classifying that slice is
            about <strong className="text-foreground">{formatUsd(costForCloudSlice, 3)}</strong> at
            March 2026 API rates.
          </p>
        </div>

        <section className="space-y-3" aria-labelledby="llm-keys-form-heading">
          <h3 id="llm-keys-form-heading" className="text-sm font-semibold">
            Add a key (optional)
          </h3>
          <div className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="llm-google">Google AI (optional)</Label>
              <p className="text-xs text-muted-foreground">Google AI Studio / Cloud console.</p>
              <Input
                id="llm-google"
                type="password"
                autoComplete="off"
                value={google}
                onChange={(e) => setGoogle(e.target.value)}
                placeholder="Google API key"
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="llm-anthropic">Anthropic (optional)</Label>
              <p className="text-xs text-muted-foreground">
                console.anthropic.com (often <span className="font-mono">sk-ant-</span>).
              </p>
              <Input
                id="llm-anthropic"
                type="password"
                autoComplete="off"
                value={anthropic}
                onChange={(e) => setAnthropic(e.target.value)}
                placeholder="Anthropic API key"
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="llm-openai">OpenAI (optional)</Label>
              <p className="text-xs text-muted-foreground">
                platform.openai.com (<span className="font-mono">sk-</span>…).
              </p>
              <Input
                id="llm-openai"
                type="password"
                autoComplete="off"
                value={openai}
                onChange={(e) => setOpenai(e.target.value)}
                placeholder="OpenAI API key"
              />
            </div>
          </div>

          {msg && (
            <p className="text-sm text-emerald-700 dark:text-emerald-500" role="status">
              {msg}
            </p>
          )}
          {err && (
            <p className="text-sm text-destructive" role="alert">
              {err}
            </p>
          )}
          <Button type="button" onClick={() => void onSave()} disabled={busy}>
            {busy ? "Saving…" : "Save keys"}
          </Button>
        </section>
      </CardContent>
    </Card>
  );
}
