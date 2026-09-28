import { useCallback, useEffect, useState } from "react";
import { api, setToken } from "../api";
import type { Me } from "../App";
import { Card, ErrorNote, useAction } from "../components/ui";
import { label, today } from "../format";

type Any = Record<string, any>;

function DataSources() {
  const [sources, setSources] = useState<Any[]>([]);
  const [status, setStatus] = useState<Any | null>(null);
  const { busy, error, run } = useAction();
  useEffect(() => {
    api<Any[]>("GET", "/api/sources").then(setSources);
  }, []);
  return (
    <Card title="Data sources">
      <div className="table-scroll">
        <table className="table compact sources">
          <thead>
            <tr>
              <th>Source</th>
              <th>Provides</th>
              <th>Licence</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id}>
                <td>
                  <strong>{s.name}</strong>
                  <div className="small muted">{s.licenceNotes}</div>
                </td>
                <td className="small">{s.provides.map(label).join(", ")}</td>
                <td>
                  <span className={`badge ${["unlicensed", "restricted"].includes(s.licenceStatus) ? "conf-limited" : ""}`}>{label(s.licenceStatus)}</span>
                </td>
                <td className="small">{s.enabled ? "enabled" : "off"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="form-row">
        <button disabled={busy} onClick={() => run(async () => setStatus(await api("GET", "/api/sources/poketrace/status")))}>
          Check PokeTrace plan &amp; quota
        </button>
        {status && (
          <span className="small">
            {status.configured
              ? `Plan ${status.plan} · ${status.active ? "active" : "inactive"} · ${status.dailyRemaining ?? "?"}/${status.dailyLimit ?? "?"} requests left · resets ${status.resetsAt ?? "?"}`
              : "Not configured — set POKETRACE_API_KEY in the server environment."}
          </span>
        )}
      </div>
      <ErrorNote error={error} />
    </Card>
  );
}

function FxRates({ canWrite }: { canWrite: boolean }) {
  const [rates, setRates] = useState<Any[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [f, setF] = useState({ baseCurrency: "EUR", quoteCurrency: "USD", rate: "", rateDate: today(), source: "", sourceUrl: "" });
  const { busy, error, run } = useAction();
  const load = useCallback(async () => setRates(await api("GET", "/api/fx-rates/latest")), []);
  useEffect(() => {
    load();
  }, [load]);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Card
      title="Exchange rates"
      actions={
        canWrite && (
          <>
            {(["daily", "last90Days", "full"] as const).map((feed) => (
              <button
                key={feed}
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await api("POST", "/api/fx-rates/import-ecb", { feed });
                    setNote(`ECB ${feed}: ${r.fetched} rates fetched, ${r.inserted} new, latest ${r.latestDate}.`);
                    await load();
                  })
                }
              >
                ECB {feed === "daily" ? "today" : feed === "last90Days" ? "90 days" : "full history"}
              </button>
            ))}
          </>
        )
      }
    >
      <p className="muted small">
        ECB reference rates import automatically every 6 hours. Foreign-currency evidence without a rate from the previous 7 days is rejected
        (NO_FX_RATE).
      </p>
      {note && <div className="note">{note}</div>}
      <div className="table-scroll audit">
        <table className="table compact">
          <thead>
            <tr>
              <th>Pair</th>
              <th className="num">Rate</th>
              <th>Date</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r) => (
              <tr key={`${r.base_currency}${r.quote_currency}`}>
                <td>
                  {r.base_currency}→{r.quote_currency}
                </td>
                <td className="num">{Number(r.rate).toFixed(4)}</td>
                <td>{r.rate_date}</td>
                <td className="small muted">{r.source}</td>
              </tr>
            ))}
            {!rates.length && (
              <tr>
                <td colSpan={4} className="muted">
                  No rates yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canWrite && (
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await api("POST", "/api/fx-rates", { ...f, rate: Number(f.rate), sourceUrl: f.sourceUrl || null });
              setF({ ...f, rate: "", source: "", sourceUrl: "" });
              await load();
            });
          }}
        >
          <input pattern="[A-Z]{3}" value={f.baseCurrency} onChange={set("baseCurrency")} title="Base" />
          <input pattern="[A-Z]{3}" value={f.quoteCurrency} onChange={set("quoteCurrency")} title="Quote" />
          <input required inputMode="decimal" placeholder="Rate" value={f.rate} onChange={set("rate")} />
          <input type="date" max={today()} value={f.rateDate} onChange={set("rateDate")} />
          <input required minLength={2} placeholder="Source (documented)" value={f.source} onChange={set("source")} />
          <input type="url" placeholder="Source URL" value={f.sourceUrl} onChange={set("sourceUrl")} />
          <button disabled={busy}>Record rate</button>
        </form>
      )}
      <ErrorNote error={error} />
    </Card>
  );
}

function Methodology({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<Any | null>(null);
  const [reviewers, setReviewers] = useState<Any[]>([]);
  const [rv, setRv] = useState({ name: "", credentials: "", organisation: "" });
  const [review, setReview] = useState({ versionId: "", reviewerId: "", reviewDate: today(), scopeStatement: "", conclusion: "" });
  const { busy, error, run } = useAction();
  const load = useCallback(async () => {
    const [m, r] = await Promise.all([api("GET", "/api/methodology"), api<Any[]>("GET", "/api/reviewers")]);
    setData(m);
    setReviewers(r);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!data) return null;
  return (
    <Card title="Methodology & independent review">
      <table className="table compact">
        <tbody>
          {data.versions.map((v: Any) => (
            <tr key={v.id}>
              <td>
                <strong>{v.id}</strong>
                <div className="small muted">effective {v.effective_from}</div>
              </td>
              <td className="small">{v.summary}</td>
              <td className="small">
                {data.reviews.filter((r: Any) => r.methodology_version_id === v.id).map((r: Any) => (
                  <div key={r.id}>
                    Reviewed by {r.reviewer_name}, {r.credentials} ({r.review_date})
                  </div>
                ))}
                {!data.reviews.some((r: Any) => r.methodology_version_id === v.id) && <span className="muted">Not independently reviewed</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        A review validates the methodology only. Reports always state that the reviewer has not certified individual valuations.
      </p>
      {isAdmin && (
        <>
          <h3>Add reviewer</h3>
          <form
            className="form-row"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("POST", "/api/reviewers", { ...rv, organisation: rv.organisation || null });
                setRv({ name: "", credentials: "", organisation: "" });
                await load();
              });
            }}
          >
            <input required placeholder="Name" value={rv.name} onChange={(e) => setRv({ ...rv, name: e.target.value })} />
            <input required placeholder="Credentials (e.g. CA, CPA)" value={rv.credentials} onChange={(e) => setRv({ ...rv, credentials: e.target.value })} />
            <input placeholder="Organisation" value={rv.organisation} onChange={(e) => setRv({ ...rv, organisation: e.target.value })} />
            <button disabled={busy}>Add reviewer</button>
          </form>
          <h3>Record a methodology review</h3>
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("POST", `/api/methodology/${review.versionId}/reviews`, {
                  reviewerId: review.reviewerId,
                  reviewDate: review.reviewDate,
                  scopeStatement: review.scopeStatement,
                  conclusion: review.conclusion,
                });
                setReview({ ...review, scopeStatement: "", conclusion: "" });
                await load();
              });
            }}
          >
            <label>
              Methodology version
              <select required value={review.versionId} onChange={(e) => setReview({ ...review, versionId: e.target.value })}>
                <option value="">—</option>
                {data.versions.map((v: Any) => (
                  <option key={v.id}>{v.id}</option>
                ))}
              </select>
            </label>
            <label>
              Reviewer
              <select required value={review.reviewerId} onChange={(e) => setReview({ ...review, reviewerId: e.target.value })}>
                <option value="">—</option>
                {reviewers.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}, {r.credentials}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Review date
              <input type="date" max={today()} value={review.reviewDate} onChange={(e) => setReview({ ...review, reviewDate: e.target.value })} />
            </label>
            <label className="span-all">
              Scope of the review (what was examined)
              <input required minLength={20} value={review.scopeStatement} onChange={(e) => setReview({ ...review, scopeStatement: e.target.value })} />
            </label>
            <label className="span-all">
              Conclusion
              <input required minLength={10} value={review.conclusion} onChange={(e) => setReview({ ...review, conclusion: e.target.value })} />
            </label>
            <div className="span-all">
              <button className="primary" disabled={busy}>
                Record review
              </button>
            </div>
          </form>
        </>
      )}
      <ErrorNote error={error} />
    </Card>
  );
}

function Users({ me }: { me: Me }) {
  const [users, setUsers] = useState<Any[]>([]);
  const [link, setLink] = useState<string | null>(null);
  const { busy, error, run } = useAction();
  const load = useCallback(async () => setUsers(await api("GET", "/api/admin/users")), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <Card title="Users & roles">
      <div className="table-scroll">
        <table className="table compact">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Joined</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  {u.display_name}
                  <div className="small muted">{u.email}</div>
                </td>
                <td>
                  <select
                    value={u.role}
                    disabled={busy || u.id === me.id}
                    onChange={(e) =>
                      run(async () => {
                        await api("PATCH", `/api/admin/users/${u.id}/role`, { role: e.target.value });
                        await load();
                      })
                    }
                  >
                    {["collector", "valuer", "admin"].map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </td>
                <td className="small">{u.created_at.slice(0, 10)}</td>
                <td>
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const r = await api("POST", `/api/admin/users/${u.id}/password-reset`);
                        setLink(`${location.origin}/#/reset/${r.token} (expires ${r.expiresAt.slice(0, 16).replace("T", " ")})`);
                      })
                    }
                  >
                    Reset link
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {link && (
        <div className="note">
          Send this one-time link to the user privately: <code>{link}</code>
        </div>
      )}
      <ErrorNote error={error} />
    </Card>
  );
}

function ChangePassword() {
  const [f, setF] = useState({ currentPassword: "", newPassword: "" });
  const [done, setDone] = useState(false);
  const { busy, error, run } = useAction();
  return (
    <Card title="Change password">
      <form
        className="form-row"
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => {
            const r = await api<{ token: string }>("POST", "/api/auth/change-password", f);
            setToken(r.token);
            setDone(true);
            setF({ currentPassword: "", newPassword: "" });
          });
        }}
      >
        <input type="password" required placeholder="Current password" value={f.currentPassword} onChange={(e) => setF({ ...f, currentPassword: e.target.value })} />
        <input type="password" required minLength={10} placeholder="New password (10+ characters)" value={f.newPassword} onChange={(e) => setF({ ...f, newPassword: e.target.value })} />
        <button disabled={busy}>Change</button>
      </form>
      {done && <div className="note">Password changed. Other sessions have been signed out.</div>}
      <ErrorNote error={error} />
    </Card>
  );
}

export function Settings({ me }: { me: Me }) {
  const isAdmin = me.role === "admin";
  return (
    <div className="stack">
      <h1>Settings</h1>
      <ChangePassword />
      <DataSources />
      <FxRates canWrite={me.role === "admin" || me.role === "valuer"} />
      <Methodology isAdmin={isAdmin} />
      {isAdmin && <Users me={me} />}
    </div>
  );
}
