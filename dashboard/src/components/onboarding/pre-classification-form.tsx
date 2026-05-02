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
 *
 * **Draft persistence:** In-progress fields are debounced to localStorage; after a
 * successful save we clear that backup. If there is no local draft, we load the
 * last POSTed values from ``GET /api/onboarding/preclassification``.
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
import { useFormDraft } from "@/hooks/use-form-draft";
import { buildApiUrl } from "@/lib/api-base";
import { fetchOnboardingPreclassificationSaved } from "@/lib/api";
import { getUserFacingErrorMessage, userMessageFromApiResponseBody } from "@/lib/user-facing-api-error";

type PreviewResponse = { self_name: string; self_aliases: string[] };

/** One localStorage + GET payload shape for this step. */
type PreclassDraft = {
  firstName: string;
  lastName: string;
  extrasRaw: string;
  accountFragmentsRaw: string;
  upiIdsRaw: string;
};

const PRECLASS_STORAGE_KEY = "arth_onboarding_preclass";

const PRECLASS_DEFAULT: PreclassDraft = {
  firstName: "",
  lastName: "",
  extrasRaw: "",
  accountFragmentsRaw: "",
  upiIdsRaw: "",
};

/** Split merged ``account_hints`` from the server back into the two text areas (heuristic: ``@`` → UPI). */
function splitHintsForForm(hints: string[]): { fragments: string; upi: string } {
  const upi: string[] = [];
  const fr: string[] = [];
  for (const h of hints) {
    const t = h.trim();
    if (!t) continue;
    if (t.includes("@")) upi.push(t);
    else fr.push(t);
  }
  return { fragments: fr.join("\n"), upi: upi.join("\n") };
}

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
  const { value: d, setValue: setD, clearDraft, restoredFromLocalStorage } = useFormDraft(
    PRECLASS_STORAGE_KEY,
    PRECLASS_DEFAULT,
  );

  const [preview, setPreview] = React.useState<PreviewResponse | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  // Same splitting rules as save — keeps preview in sync with POST /preclassification.
  const extrasList = React.useMemo(() => splitHintLines(d.extrasRaw), [d.extrasRaw]);

  const accountHintsForSave = React.useMemo(() => {
    return [...splitHintLines(d.accountFragmentsRaw), ...splitHintLines(d.upiIdsRaw)];
  }, [d.accountFragmentsRaw, d.upiIdsRaw]);

  // If the user has no local draft, hydrate from the last successful POST (server truth).
  React.useEffect(() => {
    if (restoredFromLocalStorage) return;
    let cancelled = false;
    (async () => {
      try {
        const saved = await fetchOnboardingPreclassificationSaved();
        if (cancelled) return;
        const hasServer =
          saved.first_name.trim() !== "" ||
          saved.last_name.trim() !== "" ||
          (saved.extra_aliases?.length ?? 0) > 0 ||
          (saved.account_hints?.length ?? 0) > 0;
        if (!hasServer) return;
        const { fragments, upi } = splitHintsForForm(saved.account_hints ?? []);
        setD((prev) => {
          // Do not clobber in-flight typing if the user started before the GET returned.
          if (
            prev.firstName.trim() ||
            prev.lastName.trim() ||
            prev.extrasRaw.trim() ||
            prev.accountFragmentsRaw.trim() ||
            prev.upiIdsRaw.trim()
          ) {
            return prev;
          }
          return {
            ...prev,
            firstName: saved.first_name,
            lastName: saved.last_name,
            extrasRaw: (saved.extra_aliases ?? []).join("\n"),
            accountFragmentsRaw: fragments,
            upiIdsRaw: upi,
          };
        });
      } catch {
        /* offline / non-fatal */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [restoredFromLocalStorage, setD]);

  // Debounced preview so we do not spam the API on every keystroke.
  // Pass extrasList so the server can merge nicknames into self_aliases (same as on save).
  React.useEffect(() => {
    if (!d.firstName.trim()) {
      setPreview(null);
      return;
    }
    const t = window.setTimeout(() => {
      void fetchPreview(d.firstName.trim(), d.lastName.trim(), extrasList).then(setPreview);
    }, 300);
    return () => window.clearTimeout(t);
  }, [d.firstName, d.lastName, extrasList]);

  async function onSave() {
    setMessage(null);
    setSaveError(null);
    setSaving(true);
    try {
      await savePreclassification({
        first_name: d.firstName.trim(),
        last_name: d.lastName.trim(),
        extra_aliases: extrasList,
        account_hints: accountHintsForSave,
      });
      clearDraft();
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
            value={d.firstName}
            onChange={(e) => setD((p) => ({ ...p, firstName: e.target.value }))}
            autoComplete="given-name"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="pc-last">Last name / surname</Label>
          <Input
            id="pc-last"
            placeholder='e.g. "Kuppa"'
            value={d.lastName}
            onChange={(e) => setD((p) => ({ ...p, lastName: e.target.value }))}
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
            value={d.extrasRaw}
            onChange={(e) => setD((p) => ({ ...p, extrasRaw: e.target.value }))}
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
            value={d.accountFragmentsRaw}
            onChange={(e) => setD((p) => ({ ...p, accountFragmentsRaw: e.target.value }))}
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
            value={d.upiIdsRaw}
            onChange={(e) => setD((p) => ({ ...p, upiIdsRaw: e.target.value }))}
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
        {/* <p className="text-sm text-muted-foreground">
          For family or friends who often appear in your UPI messages, add them under&nbsp;
          <span>Settings &rarr; Classification</span>
          — optional, but it helps label those payments correctly.
        </p> */}

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
        <Button type="button" onClick={() => void onSave()} disabled={saving || !d.firstName.trim()}>
          {saving ? "Saving…" : "Save identity"}
        </Button>
      </CardFooter>
    </Card>
  );
}
