"use client";

/**
 * Pre-classification step (Track 2 Phase 3a).
 *
 * Banks often print your name as ``LASTNAME FIRSTNAMES`` in the narration. We
 * collect first + last separately so the backend can build **safe** substring
 * aliases (we deliberately skip a bare surname-only alias — it would match
 * relatives who share that surname). Matching is case-insensitive: aliases are
 * stored uppercase and compared to uppercased bank text.
 *
 * Flow for the learner:
 * 1. Type your first name(s) and surname — watch the live preview.
 * 2. Optionally add nicknames / alternate spellings your bank uses.
 * 3. Optionally add account/card fragments and UPI IDs — stored as ``account_hints_json``
 *    for rules-based self-transfer detection (substring match on bank narrations).
 * 4. Click **Save identity** — this hits ``POST /api/onboarding/preclassification``.
 * 5. Add family contacts under **Settings → Classification** (contacts API)
 *    — optional for labelling friend/family UPI payments.
 */

import * as React from "react";

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

async function fetchPreview(
  first: string,
  last: string,
  /** Same parsing as save — each string becomes an uppercase alias on the server. */
  extraAliases: string[],
): Promise<PreviewResponse | null> {
  const q = new URLSearchParams({ first_name: first, last_name: last });
  for (const a of extraAliases) {
    q.append("extra_aliases", a);
  }
  const res = await fetch(buildApiUrl(`/api/onboarding/preclassification/preview?${q}`), {
    credentials: "include",
  });
  if (!res.ok) return null;
  return res.json() as Promise<PreviewResponse>;
}

/** Split user textarea input on newlines or commas (same as extra aliases). */
function splitHintLines(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

async function savePreclassification(payload: {
  first_name: string;
  last_name: string;
  extra_aliases: string[];
  /** Account/card fragments and full UPI IDs merged server-side into ``account_hints_json``. */
  account_hints: string[];
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
  /** First/last-4 or other digits that appear in bank messages (one per line or comma-separated). */
  const [accountFragmentsRaw, setAccountFragmentsRaw] = React.useState("");
  /** Full UPI handles (e.g. name@paytm) — merged into the same ``account_hints`` list as fragments. */
  const [upiIdsRaw, setUpiIdsRaw] = React.useState("");
  const [preview, setPreview] = React.useState<PreviewResponse | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  // Same splitting rules as save — keeps preview in sync with POST /preclassification.
  const extrasList = React.useMemo(() => splitHintLines(extrasRaw), [extrasRaw]);

  const accountHintsForSave = React.useMemo(() => {
    return [...splitHintLines(accountFragmentsRaw), ...splitHintLines(upiIdsRaw)];
  }, [accountFragmentsRaw, upiIdsRaw]);

  // Debounced preview so we do not spam the API on every keystroke.
  // Pass extrasList so the server can merge nicknames into self_aliases (same as on save).
  React.useEffect(() => {
    if (!firstName.trim()) {
      setPreview(null);
      return;
    }
    const t = window.setTimeout(() => {
      void fetchPreview(firstName.trim(), lastName.trim(), extrasList).then(setPreview);
    }, 300);
    return () => window.clearTimeout(t);
  }, [firstName, lastName, extrasList]);

  async function onSave() {
    setMessage(null);
    setSaveError(null);
    setSaving(true);
    try {
      await savePreclassification({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        extra_aliases: extrasList,
        account_hints: accountHintsForSave,
      });
      setMessage(
        "Saved — we will use your names and hints to recognise money you move to yourself.",
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
          name in bank text. All fields are case-agnostic.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2">
          <Label htmlFor="pc-first">First name</Label>
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
            Don't worry about your last name matching your family. We handle it.
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
        <div className="grid gap-2">
          <Label htmlFor="pc-account-hints">Account &amp; card number fragments (optional)</Label>
          <Textarea
            id="pc-account-hints"
            placeholder={
              "One per line or comma-separated — first four/last four numbers (ignore the zeroes)."
            }
            value={accountFragmentsRaw}
            onChange={(e) => setAccountFragmentsRaw(e.target.value)}
            rows={3}
          />
          <p className="text-xs text-muted-foreground">
            This helps catch transfers your name/alias does not appear on.
          </p>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="pc-upi-ids">Your UPI IDs (optional)</Label>
          <Textarea
            id="pc-upi-ids"
            placeholder={"One per line or comma-separated.\ne.g. yourname@okicici"}
            value={upiIdsRaw}
            onChange={(e) => setUpiIdsRaw(e.target.value)}
            rows={2}
          />
          <p className="text-xs text-muted-foreground">
            This helps identify self-transfers and prevent double counting in expenses.
          </p>
        </div>
        {preview && (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <div className="font-medium">Names we will use to recognise you:</div>
            <div className="mt-2 space-y-2 font-mono text-xs leading-relaxed">
              <div>
                {preview.self_aliases.length ? preview.self_aliases.join(" · ") : "—"}
              </div>
            </div>
       
          </div>
        )}
        <p className="text-sm text-muted-foreground">
          For family or friends who often appear in your UPI messages, add them under&nbsp;
          <span>Settings &rarr; Classification</span>
          — optional, but it helps label those payments correctly.
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
