"use client";

/**
 * First-run setup (DESKTOP_PREREQS item 3) + Track 2 onboarding wizard (Phase 5b).
 *
 * Flow:
 *   1. If the SQLite DB has **no** users yet → simple registration form.
 *   2. If users exist but the browser has **no** session → nudge to ``/login``.
 *   3. Once authenticated, optionally collect PDF passwords (same as before).
 *   4. Then mount ``OnboardingWizard`` — Gmail discovery, identity, chunk backfill,
 *      inline classification pauses, gap detection, goals, and completion.
 *
 * The wizard itself lives in ``src/components/onboarding/onboarding-wizard.tsx`` so we
 * can reuse it from Settings → **Connect account** without duplicating logic.
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { Button } from "@/components/ui/button";
import {
  completeSetupWizard,
  fetchSetupStatus,
  registerFirstUser,
  saveSetupSecrets,
} from "@/lib/api";
import { buildApiUrl } from "@/lib/api-base";

async function authMeNoRedirect(): Promise<{ authenticated: boolean; username?: string | null }> {
  const res = await fetch(buildApiUrl("/api/auth/me"), { credentials: "include" });
  if (res.status === 401) {
    return { authenticated: false, username: null };
  }
  if (!res.ok) {
    return { authenticated: false, username: null };
  }
  return res.json() as Promise<{ authenticated: boolean; username?: string | null }>;
}

export default function SetupPage() {
  const router = useRouter();
  const [loading, setLoading] = React.useState(true);
  const [step, setStep] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  const [regUser, setRegUser] = React.useState("");
  const [regPw, setRegPw] = React.useState("");
  const [secretsJson, setSecretsJson] = React.useState(
    '{\n  "HDFC_STATEMENT_PASSWORD": ""\n}',
  );

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [status, auth] = await Promise.all([
          fetchSetupStatus(),
          authMeNoRedirect(),
        ]);
        if (cancelled) return;
        if (status.setup_completed && auth.authenticated) {
          router.replace("/");
          return;
        }
        if (!status.has_users) {
          setStep(0);
        } else if (!auth.authenticated) {
          setStep(1);
        } else {
          setStep(2);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load setup status");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await registerFirstUser(regUser.trim(), regPw);
      setStep(1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  }

  async function onSaveSecrets(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const parsed = JSON.parse(secretsJson) as Record<string, string>;
      await saveSetupSecrets(parsed);
      setStep(3);
    } catch {
      setError("Secrets must be valid JSON object mapping env key → password string.");
    }
  }

  async function onWizardFinished() {
    setError(null);
    try {
      await completeSetupWizard();
      router.replace("/");
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not finalize setup flags");
    }
  }

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading setup…</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-background p-4">
      <div className="w-full max-w-4xl rounded-xl border bg-card p-6 sm:p-10 shadow-sm">
        {step < 3 && (
          <>
            <h1 className="text-xl font-semibold">Welcome to Arth</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Local-first setup — your data stays on this machine.
            </p>
          </>
        )}

        {error && (
          <p className="mt-4 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        {step === 0 && (
          <form onSubmit={onRegister} className="mt-6 space-y-4 max-w-lg">
            <h2 className="text-sm font-medium">Create your account</h2>
            <input
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Username"
              value={regUser}
              onChange={(e) => setRegUser(e.target.value)}
              required
            />
            <input
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              type="password"
              placeholder="Password"
              value={regPw}
              onChange={(e) => setRegPw(e.target.value)}
              required
            />
            <Button type="submit" className="w-full">
              Register
            </Button>
          </form>
        )}

        {step === 1 && (
          <div className="mt-6 space-y-4 max-w-lg">
            <p className="text-sm text-muted-foreground">
              Sign in with the account you just created (or an existing one).
            </p>
            <Button
              className="w-full"
              variant="secondary"
              onClick={() => router.push("/login?from=/setup")}
            >
              Go to sign in
            </Button>
          </div>
        )}

        {step === 2 && (
          <form onSubmit={onSaveSecrets} className="mt-6 space-y-4 max-w-lg">
            <h2 className="text-sm font-medium">PDF passwords (optional)</h2>
            <p className="text-xs text-muted-foreground">
              JSON object whose keys match <code className="rounded bg-muted px-1">.env</code> names
              (e.g. HDFC_STATEMENT_PASSWORD). You can skip and rely on{" "}
              <code className="rounded bg-muted px-1">.env</code> instead.
            </p>
            <textarea
              className="min-h-[120px] w-full rounded-md border bg-background p-2 font-mono text-xs"
              value={secretsJson}
              onChange={(e) => setSecretsJson(e.target.value)}
            />
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={() => setStep(3)}>
                Skip
              </Button>
              <Button type="submit" className="flex-1">
                Save & continue
              </Button>
            </div>
          </form>
        )}

        {step === 3 && (
          <div className="mt-4">
            <OnboardingWizard
              mode="setup"
              onExitFirstStep={() => setStep(2)}
              onFinished={() => void onWizardFinished()}
            />
          </div>
        )}
      </div>
    </div>
  );
}
