import { useEffect, useState } from "react";
import { api } from "../api";
import { navigate } from "../App";
import { Card, ErrorNote, useAction } from "../components/ui";
import { label, toMinor, today } from "../format";

interface Identity {
  id: string;
  game: string;
  product_type: string;
  set_code: string;
  set_name: string;
  card_number: string | null;
  card_name: string;
  language: string;
  edition: string | null;
  variant: string | null;
}

const GAMES = ["pokemon", "one_piece", "mtg", "yugioh", "lorcana", "other"];

function NewIdentityForm({ onCreated }: { onCreated: (i: Identity) => void }) {
  const [f, setF] = useState({
    game: "pokemon",
    productType: "single",
    category: "card",
    setCode: "",
    setName: "",
    cardNumber: "",
    cardName: "",
    language: "en",
    edition: "",
    variant: "holo",
  });
  const { busy, error, run } = useAction();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="form-grid"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () =>
          onCreated(
            await api("POST", "/api/catalog/cards", {
              ...f,
              cardNumber: f.cardNumber || null,
              edition: f.edition || null,
              variant: f.variant || null,
            }),
          ),
        );
      }}
    >
      <label>
        Game
        <select value={f.game} onChange={set("game")}>
          {GAMES.map((g) => (
            <option key={g} value={g}>
              {label(g)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Type
        <select value={f.productType} onChange={set("productType")}>
          <option value="single">Single card</option>
          <option value="sealed">Sealed product</option>
        </select>
      </label>
      <label>
        Card / product name
        <input required value={f.cardName} onChange={set("cardName")} />
      </label>
      <label>
        Set code
        <input required value={f.setCode} onChange={set("setCode")} placeholder="e.g. base1, OP01" />
      </label>
      <label>
        Set name
        <input required value={f.setName} onChange={set("setName")} />
      </label>
      <label>
        Card number
        <input value={f.cardNumber} onChange={set("cardNumber")} placeholder="e.g. 4/102" />
      </label>
      <label>
        Language
        <input required value={f.language} onChange={set("language")} />
      </label>
      <label>
        Edition / printing
        <input value={f.edition} onChange={set("edition")} placeholder="1st, unlimited, shadowless…" />
      </label>
      <label>
        Variant
        <select value={f.variant} onChange={set("variant")}>
          {["normal", "holo", "reverse_holo", "alt_art", "full_art", "secret_rare", ""].map((v) => (
            <option key={v} value={v}>
              {v ? label(v) : "—"}
            </option>
          ))}
        </select>
      </label>
      {f.productType === "sealed" && (
        <label>
          Category
          <select value={f.category} onChange={set("category")}>
            {["booster_box", "etb", "tin", "pack", "bundle", "other"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </label>
      )}
      <ErrorNote error={error} />
      <div className="span-all">
        <button className="primary" disabled={busy}>
          Create catalogue entry
        </button>
      </div>
    </form>
  );
}

interface Candidate {
  externalId: string;
  cardName: string;
  setCode: string;
  cardNumber: string | null;
  imageUrl: string | null;
}

/** Search the open TCGdex catalogue and import the chosen printing into the local catalogue. */
function TcgdexSearch({ onImported }: { onImported: (i: Identity) => void }) {
  const [q, setQ] = useState("");
  const [language, setLanguage] = useState("en");
  const [results, setResults] = useState<Candidate[]>([]);
  const [pick, setPick] = useState<{ id: string; edition: string; variant: string } | null>(null);
  const { busy, error, run } = useAction();
  return (
    <div className="stack">
      <form
        className="form-row"
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => setResults(await api("GET", `/api/catalog/remote?source=tcgdex&q=${encodeURIComponent(q)}&language=${language}`)));
        }}
      >
        <input required minLength={2} placeholder="Card name, e.g. Charizard" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          {["en", "ja", "fr", "de", "it", "es", "pt"].map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
        <button className="primary" disabled={busy}>Search</button>
      </form>
      <ErrorNote error={error} />
      <ul className="results">
        {results.map((r) => (
          <li key={r.externalId} className={pick?.id === r.externalId ? "selected" : ""} onClick={() => setPick({ id: r.externalId, edition: "", variant: "holo" })}>
            <strong>{r.cardName}</strong> <span className="muted">{r.setCode} #{r.cardNumber}</span> <span className="small muted">({r.externalId})</span>
          </li>
        ))}
      </ul>
      {pick && (
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const res = await api<{ identity: Identity }>("POST", "/api/catalog/import", {
                source: "tcgdex",
                externalId: pick.id,
                language,
                edition: pick.edition || null,
                variant: pick.variant || null,
              });
              onImported(res.identity);
            });
          }}
        >
          <span className="small">Printing for {pick.id}:</span>
          <input placeholder="Edition (1st, unlimited…)" value={pick.edition} onChange={(e) => setPick({ ...pick, edition: e.target.value })} />
          <select value={pick.variant} onChange={(e) => setPick({ ...pick, variant: e.target.value })}>
            {["normal", "holo", "reverse_holo", "alt_art", "full_art", "secret_rare"].map((v) => (
              <option key={v} value={v}>{label(v)}</option>
            ))}
          </select>
          <button className="primary" disabled={busy}>Import &amp; select</button>
        </form>
      )}
      <p className="muted small">TCGdex card data is MIT-licensed; artwork and trademarks belong to their owners.</p>
    </div>
  );
}

export function AddAsset({ collection }: { collection: { id: string; base_currency: string } }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Identity[]>([]);
  const [selected, setSelected] = useState<Identity | null>(null);
  const [mode, setMode] = useState<"local" | "tcgdex" | "create">("local");
  const [f, setF] = useState({
    quantity: "1",
    acquisitionDate: today(),
    price: "",
    currency: collection.base_currency,
    source: "",
    graded: false,
    gradingCompany: "PSA",
    grade: "",
    certNumber: "",
    condition: "NM",
    notes: "",
  });
  const { busy, error, run } = useAction();

  useEffect(() => {
    const t = setTimeout(() => {
      api<Identity[]>("GET", `/api/catalog/search?q=${encodeURIComponent(q)}`).then(setResults, () => undefined);
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    run(async () => {
      const sealed = selected.product_type === "sealed";
      const asset = await api<{ id: string }>("POST", `/api/collections/${collection.id}/assets`, {
        cardIdentityId: selected.id,
        quantity: Number(f.quantity),
        acquisitionDate: f.acquisitionDate,
        acquisitionPriceMinor: toMinor(f.price || "0"),
        acquisitionCurrency: f.currency,
        acquisitionSource: f.source || null,
        notes: f.notes || null,
        gradingCompany: !sealed && f.graded ? f.gradingCompany : null,
        grade: !sealed && f.graded ? f.grade : null,
        certNumber: !sealed && f.graded ? f.certNumber || null : null,
        condition: !sealed && !f.graded ? f.condition : null,
      });
      navigate({ name: "asset", id: asset.id });
    });
  };

  return (
    <div className="stack">
      <h1>Add asset</h1>
      <Card
        title="1 · Select the card or product"
        actions={
          <div className="button-row">
            {(["local", "tcgdex", "create"] as const).map((m) => (
              <button key={m} className={mode === m ? "primary" : ""} onClick={() => setMode(m)}>
                {m === "local" ? "My catalogue" : m === "tcgdex" ? "Search TCGdex (Pokémon)" : "Create manually"}
              </button>
            ))}
          </div>
        }
      >
        {mode === "create" && (
          <NewIdentityForm
            onCreated={(i) => {
              setSelected(i);
              setMode("local");
            }}
          />
        )}
        {mode === "tcgdex" && <TcgdexSearch onImported={(i) => { setSelected(i); setMode("local"); }} />}
        {mode === "local" && (
          <>
            <input className="search" placeholder="Search by name, set or number…" value={q} onChange={(e) => setQ(e.target.value)} />
            <ul className="results">
              {results.map((r) => (
                <li key={r.id} className={selected?.id === r.id ? "selected" : ""} onClick={() => setSelected(r)}>
                  <strong>{r.card_name}</strong> <span className="muted">{r.set_name} {r.card_number ? `#${r.card_number}` : ""}</span>
                  <div className="small muted">
                    {label(r.game)} · {r.language.toUpperCase()} · {r.edition ?? "—"} · {label(r.variant) || "—"} · {r.product_type}
                  </div>
                </li>
              ))}
              {!results.length && (
                <li className="muted">
                  No matches in your catalogue. Try <button className="link" onClick={() => setMode("tcgdex")}>TCGdex</button> or{" "}
                  <button className="link" onClick={() => setMode("create")}>create it manually</button>.
                </li>
              )}
            </ul>
          </>
        )}
      </Card>
      {selected && (
        <Card title={`2 · Details for ${selected.card_name}`}>
          <form className="form-grid" onSubmit={submit}>
            <label>
              Quantity
              <input type="number" min={1} required value={f.quantity} onChange={set("quantity")} />
            </label>
            <label>
              Acquisition date
              <input type="date" max={today()} required value={f.acquisitionDate} onChange={set("acquisitionDate")} />
            </label>
            <label>
              Total price paid
              <input inputMode="decimal" required value={f.price} onChange={set("price")} placeholder="0.00" />
            </label>
            <label>
              Currency
              <input pattern="[A-Z]{3}" required value={f.currency} onChange={set("currency")} />
            </label>
            <label>
              Acquisition source
              <input value={f.source} onChange={set("source")} placeholder="eBay, card show, LGS…" />
            </label>
            {selected.product_type !== "sealed" && (
              <label className="inline">
                <input type="checkbox" checked={f.graded} onChange={set("graded")} /> Graded slab
              </label>
            )}
            {selected.product_type !== "sealed" && f.graded && (
              <>
                <label>
                  Grading company
                  <select value={f.gradingCompany} onChange={set("gradingCompany")}>
                    {["PSA", "BGS", "CGC", "SGC", "TAG", "ACE", "Other"].map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Grade
                  <input required value={f.grade} onChange={set("grade")} placeholder="10, 9.5…" />
                </label>
                <label>
                  Certification number
                  <input value={f.certNumber} onChange={set("certNumber")} />
                </label>
              </>
            )}
            {selected.product_type !== "sealed" && !f.graded && (
              <label>
                Condition
                <select value={f.condition} onChange={set("condition")}>
                  {["M", "NM", "LP", "MP", "HP", "DMG"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}
            <label className="span-all">
              Notes
              <input value={f.notes} onChange={set("notes")} />
            </label>
            <ErrorNote error={error} />
            <div className="span-all">
              <button className="primary" disabled={busy}>
                Add to collection
              </button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
