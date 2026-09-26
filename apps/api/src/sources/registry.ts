import type { Config } from "../config.js";
import { DemoAdapter } from "./demo.js";
import { SOURCE_DEFINITIONS } from "./definitions.js";
import { RestrictedSourceAdapter } from "./restricted.js";
import { TcgdexAdapter } from "./tcgdex.js";
import type { SourceAdapter } from "./types.js";

export class SourceRegistry {
  private readonly adapters = new Map<string, SourceAdapter>();

  register(adapter: SourceAdapter): void {
    this.adapters.set(adapter.id, adapter);
  }

  get(id: string): SourceAdapter | undefined {
    return this.adapters.get(id);
  }

  list() {
    return SOURCE_DEFINITIONS.map((def) => {
      const adapter = this.adapters.get(def.id);
      return {
        ...def,
        enabled: def.licenceStatus === "user_supplied" ? true : (adapter?.enabled() ?? false),
        automatedEvidence: Boolean(adapter?.fetchEvidence) && (adapter?.enabled() ?? false),
        catalogue: Boolean(adapter?.searchCatalog) && (adapter?.enabled() ?? false),
      };
    });
  }
}

export function createRegistry(config: Config, fetchImpl: typeof fetch = fetch): SourceRegistry {
  const registry = new SourceRegistry();
  registry.register(new DemoAdapter(config.enableDemoSource));
  registry.register(new TcgdexAdapter(config.enableTcgdex, fetchImpl));
  for (const id of ["ebay_marketplace_insights", "cardmarket", "tcgplayer", "pricecharting", "psa", "auction_house"]) {
    registry.register(new RestrictedSourceAdapter(id));
  }
  return registry;
}
