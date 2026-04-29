"use client";

/**
 * Optional LLM API keys during onboarding (Track 2 Phase 3c).
 *
 * Keys are stored encrypted in the same ``UserSecrets`` row as PDF passwords.
 * If you skip this, the pipeline stays **rules-only** (plus whatever you teach it
 * in the classification batch). That is a supported path — not a second-class mode.
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
import { buildApiUrl } from "@/lib/api-base";
import { getUserFacingErrorMessage, userMessageFromApiResponseBody } from "@/lib/user-facing-api-error";

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
    throw new Error(userMessageFromApiResponseBody(t) || "Could not save keys. Try again.");
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
      setMsg("Saved — keys are encrypted at rest. Clear a field and save again to remove a key.");
    } catch (e) {
      setErr(getUserFacingErrorMessage(e) || "Could not save keys. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Optional: smarter auto-labels</CardTitle>
        <CardDescription>
          Paste <strong>one</strong> key from a provider you already use if you want extra help
          guessing merchant names from messy bank text. Leave all fields blank to stay fully local —
          Arth still works with built-in rules; we just ask you to confirm a bit more often when
          there is no key.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid gap-1">
          <Label htmlFor="llm-openai">OpenAI (optional)</Label>
          <p className="text-xs text-muted-foreground">
            From platform.openai.com → API keys (starts with <span className="font-mono">sk-</span>).
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
        <div className="grid gap-1">
          <Label htmlFor="llm-anthropic">Anthropic (optional)</Label>
          <p className="text-xs text-muted-foreground">
            From console.anthropic.com (often starts with <span className="font-mono">sk-ant-</span>).
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
          <Label htmlFor="llm-google">Google AI (optional)</Label>
          <p className="text-xs text-muted-foreground">From Google AI Studio / Cloud console.</p>
          <Input
            id="llm-google"
            type="password"
            autoComplete="off"
            value={google}
            onChange={(e) => setGoogle(e.target.value)}
            placeholder="Google API key"
          />
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
      </CardContent>
    </Card>
  );
}
