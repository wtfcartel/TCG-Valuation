import type { SourceAdapter } from "./types.js";
import { SourceNotConfiguredError } from "./types.js";
import { SOURCE_DEFINITIONS } from "./definitions.js";

/**
 * Placeholder for a source that needs a commercial licence or partner approval before any
 * integration is written. It exists so the registry, UI and reports can show the source and
 * its status, and fails closed if called.
 */
export class RestrictedSourceAdapter implements SourceAdapter {
  constructor(readonly id: string) {}

  enabled(): boolean {
    return false;
  }

  async fetchEvidence(): Promise<never> {
    const def = SOURCE_DEFINITIONS.find((s) => s.id === this.id);
    throw new SourceNotConfiguredError(this.id, def?.licenceNotes ?? "licence required");
  }
}
