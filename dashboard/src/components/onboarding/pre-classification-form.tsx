"use client";

/**
 * Pre-classification step (Track 2 Phase 3a).
 *
 * Banks often print your name as ``LASTNAME FIRSTNAMES`` in the narration. We
 * collect first + last separately so the backend can build **safe** substring
 * aliases (we deliberately skip a bare surname-only alias — it would match
 * relatives who share that surname).
 *
 * Flow for the learner:
 * 1. Type your first name(s) and surname — watch the live preview.
 * 2. Optionally add nicknames / alternate spellings your bank uses.
 * 3. Click **Save identity** — this hits ``POST /api/onboarding/preclassification``.
 * 4. Add UPI / family hints under **Settings → Classification** (contacts API)
 *    — we link there so you are not blocked on this single form.
 */

import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { buildApiUrl } from "@/lib/api-base";
import { getUserFacingErrorMessage, userMessageFromApiResponseBody } from "@/lib/user-facing-api-error";

type PreviewResponse = { self_name: string; self_aliases: string[] };

async function fetchPreview(first: string, last: string): Promise<PreviewResponse | null> {
  const q = new URLSearchParams({ first_name: first, last_name: last });
  const res = await fetch(buildApiUrl(`/api/onboarding/preclassification/preview?${q}`), {
    credentials: "include",
  });
  if (!res.ok) return null;
  return res.json() as Promise<PreviewResponse>;
}

async function savePreclassification(payload: {
  first_name: string;
  last_name: string;
  extra_aliases: string[];
}): Promise<void> {
  const res = await fetch(buildApiUrl("/api/onboarding/preclassification"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const t = await res.text();
  if (!res.ok) {
    throw new Error(userMessageFromApiResponseBody(t) || "Could not save. Try again.");
  }
}

export function PreClassificationForm() {
  const [firstName, setFirstName] = React.useState("");
  const [lastName, setLastName] = React.useState("");
  const [extrasRaw, setExtrasRaw] = React.useState("");
  const [preview, setPreview] = React.useState<PreviewResponse | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  // Debounced preview so we do not spam the API on every keystroke.
  React.useEffect(() => {
    if (!firstName.trim()) {
      setPreview(null);
      return;
    }
    const t = window.setTimeout(() => {
      void fetchPreview(firstName.trim(), lastName.trim()).then(setPreview);
    }, 300);
    return () => window.clearTimeout(t);
  }, [firstName, lastName]);

  const extrasList = React.useMemo(
    () =>
      extrasRaw
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [extrasRaw],
  );

  async function onSave() {
    setMessage(null);
    setSaveError(null);
    setSaving(true);
    try {
      await savePreclassification({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        extra_aliases: extrasList,
      });
      setMessage(
        "Saved — when we read your bank messages, we will use these names to recognise you.",
      );
    } catch (e) {
      setSaveError(getUserFacingErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Your name on bank statements</CardTitle>
        <CardDescription>
          We use this to label <strong>money you move to yourself</strong> and to recognise your own
          name in bank text (including UPI notes — the short text that travels with a transfer in
          India). Arth already ships with built-in hints for common
          merchants (food delivery, streaming, etc.) — nothing to paste here.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2">
          <Label htmlFor="pc-first">First name(s)</Label>
          <Input
            id="pc-first"
            placeholder='e.g. "Sai Sashank"'
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            autoComplete="given-name"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="pc-last">Last name / surname</Label>
          <Input
            id="pc-last"
            placeholder='e.g. "Kuppa"'
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            autoComplete="family-name"
          />
          <p className="text-xs text-muted-foreground">
            We never add your surname <strong>by itself</strong> as a match — too many false matches
            when relatives share it — but we do add safe combinations like{" "}
            <span className="font-mono">LAST FIRST</span> (how many Indian banks print your name).
          </p>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="pc-extras">Extra aliases (optional)</Label>
          <Textarea
            id="pc-extras"
            placeholder={"One nickname per line, or comma-separated.\ne.g. SK KUPPA"}
            value={extrasRaw}
            onChange={(e) => setExtrasRaw(e.target.value)}
            rows={3}
          />
        </div>
        {preview && (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <div className="font-medium">Live preview</div>
            <div className="mt-1 text-muted-foreground">Display name: {preview.self_name}</div>
            <div className="mt-2 font-mono text-xs leading-relaxed">
              {preview.self_aliases.length ? preview.self_aliases.join(" · ") : "—"}
            </div>
          </div>
        )}
        <p className="text-sm text-muted-foreground">
          For <strong>family or friends</strong> who often appear in your UPI messages, add them under{" "}
          <Link href="/settings" className="text-primary underline">
            Settings
          </Link>{" "}
          → Classification — optional, but it helps label those payments correctly.
        </p>
        {message && (
          <p className="text-sm text-emerald-700 dark:text-emerald-500" role="status">
            {message}
          </p>
        )}
        {saveError && (
          <p className="text-sm text-destructive" role="alert">
            {saveError}
          </p>
        )}
      </CardContent>
      <CardFooter>
        <Button type="button" onClick={() => void onSave()} disabled={saving || !firstName.trim()}>
          {saving ? "Saving…" : "Save identity"}
        </Button>
      </CardFooter>
    </Card>
  );
}
