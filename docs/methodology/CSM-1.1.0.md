# Cardcore Comparable Sales Method — version CSM-1.1.0

Effective 2026-09-28. **Identical to [CSM-1.0.0](CSM-1.0.0.md) except for one added screening rule.** Valuations recorded under CSM-1.0.0 keep that version and are reproduced without this rule (`deduplicateTransactions` is absent from its stored parameters).

## Change: one copy per transaction (`DUPLICATE_TRANSACTION`)

The same marketplace sale can reach Cardcore through several sources. For example, an eBay sale may arrive via the PokeTrace API, a saved eBay results page and a user's CSV. Counting it more than once would overweight that sale in the three-sale mean.

- Observations that carry a marketplace transaction key (currently `ebay:<item id>`) are grouped by that key.
- Within a group, one copy is used. Sources rank licensed → open → user-supplied → synthetic → unlicensed/scraped, and then by reliability tier; ties go to the lowest observation ID.
- Every other copy is recorded as considered and rejected with code `DUPLICATE_TRANSACTION`, naming the source whose copy was used.

All other rules and parameters are unchanged.
