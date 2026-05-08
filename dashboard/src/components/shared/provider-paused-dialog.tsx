"use client";

/**
 * Blocking dialog when every configured cloud provider failed for this step.
 * Shared by onboarding mail import and Ask Arth chat — copy follows Arth guidelines (no jargon).
 */

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { ProviderFailurePayload } from "@/lib/api";

function providerDisplayName(provider: string): string {
  switch (provider) {
    case "openai":
      return "OpenAI";
    case "anthropic":
      return "Anthropic";
    case "google":
      return "Google AI";
    default:
      return "your provider";
  }
}

function headlineForFailure(f: ProviderFailurePayload): string {
  switch (f.error_type) {
    case "rate_limit":
      return `${providerDisplayName(f.provider)} is busy`;
    case "billing":
      return `${providerDisplayName(f.provider)} needs credit`;
    case "auth":
      return `Key for ${providerDisplayName(f.provider)} isn’t working`;
    default:
      return `Couldn’t reach ${providerDisplayName(f.provider)}`;
  }
}

function bodyForFailure(f: ProviderFailurePayload): string {
  const name = providerDisplayName(f.provider);
  switch (f.error_type) {
    case "rate_limit":
      return `${name} hit its request limit for now. Wait a minute and try again — or use a different provider’s key.`;
    case "billing":
      return `${name} says there isn’t enough credit on that account. Top it up in their console, or switch to another provider.`;
    case "auth":
      return `${name} rejected the key — it may have been revoked or pasted wrong. Remove it and add the correct one.`;
    default:
      return f.message.trim() || `${name} didn’t respond as expected. Try again or switch providers.`;
  }
}

export type ProviderPausedContext = "import" | "chat";

export type ProviderPausedDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  failures: ProviderFailurePayload[];
  context: ProviderPausedContext;
  /** Import: goes back to add onboarding keys. Chat: navigate to Settings. */
  onSwitchProvider: () => void;
  /** Retry the same operation (re-run import stream or resend last chat message). */
  onTryAgain: () => void;
};

export function ProviderPausedDialog({
  open,
  onOpenChange,
  failures,
  context,
  onSwitchProvider,
  onTryAgain,
}: ProviderPausedDialogProps) {
  const switchLabel =
    context === "import" ? "Add a different key" : "Update keys in Settings";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>All providers hit a wall</DialogTitle>
          <DialogDescription className="text-left">
            Arth tried each key you set up. Nothing went through — here&apos;s what came back.
          </DialogDescription>
        </DialogHeader>

        <ul className="flex flex-col gap-3 text-sm text-muted-foreground">
          {failures.map((f, i) => (
            <li
              key={`${f.provider}-${f.error_type}-${i}`}
              className="rounded-lg border border-border bg-muted/30 px-3 py-2"
            >
              <p className="font-medium text-foreground">{headlineForFailure(f)}</p>
              <p className="mt-1">{bodyForFailure(f)}</p>
            </li>
          ))}
        </ul>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => void onSwitchProvider()}>
            {switchLabel}
          </Button>
          <Button type="button" onClick={() => void onTryAgain()}>
            Try again
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
