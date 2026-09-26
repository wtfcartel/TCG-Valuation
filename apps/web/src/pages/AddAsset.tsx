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

export function AddAsset({ collection }: { collection: { id: string; base_currency: string } }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Identity[]>([]);
  const [selected, setSelected] = useState<Identity | null>(null);
  const [creating, setCreating] = useState(false);
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
      <Card title="1 · Select the card or product" actions={<button onClick={() => setCreating(!creating)}>{creating ? "Search instead" : "Not listed? Create"}</button>}>
        {creating ? (
          <NewIdentityForm
            onCreated={(i) => {
              setSelected(i);
              setCreating(false);
            }}
          />
        ) : (
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
              {!results.length && <li className="muted">No matches in the catalogue.</li>}
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
