import type { Config } from "../config.js";
import { DemoAdapter } from "./demo.js";
import { sourceDefinitions, type SourceDefinition } from "./definitions.js";
import { PokeTraceAdapter } from "./poketrace.js";
import { RestrictedSourceAdapter } from "./restricted.js";
import { TcgdexAdapter } from "./tcgdex.js";
import type { SourceAdapter } from "./types.js";

export class SourceRegistry {
  private readonly adapters = new Map<string, SourceAdapter>();

  constructor(private readonly definitions: SourceDefinition[] = sourceDefinitions()) {}

  register(adapter: SourceAdapter): void {
    this.adapters.set(adapter.id, adapter);
  }

  get(id: string): SourceAdapter | undefined {
    return this.adapters.get(id);
  }

  list() {
    return this.definitions.map((def) => {
      const adapter = this.adapters.get(def.id);
      return {
        ...def,
        enabled: def.licenceStatus === "user_supplied" || def.id === "ebay_sold_scrape" ? true : (adapter?.enabled() ?? false),
        automatedEvidence: Boolean(adapter?.fetchEvidence) && (adapter?.enabled() ?? false),
        catalogue: Boolean(adapter?.searchCatalog) && (adapter?.enabled() ?? false),
      };
    });
  }
}

export function createRegistry(config: Config, fetchImpl: typeof fetch = fetch): SourceRegistry {
  const registry = new SourceRegistry(sourceDefinitions({ poketraceCommercialLicence: config.poketraceCommercialLicence }));
  registry.register(new DemoAdapter(config.enableDemoSource));
  registry.register(new PokeTraceAdapter(config.poketraceApiKey, fetchImpl));
  registry.register(new TcgdexAdapter(config.enableTcgdex, fetchImpl));
  for (const id of ["ebay_marketplace_insights", "cardmarket", "tcgplayer", "pricecharting", "psa", "auction_house"]) {
    registry.register(new RestrictedSourceAdapter(id));
  }
  return registry;
}
