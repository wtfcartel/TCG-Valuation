import { useState } from "react";
import { api, setToken } from "../api";
import { ErrorNote, useAction } from "../components/ui";

export function AuthPage({ onAuthed }: { onAuthed: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", displayName: "", baseCurrency: "USD" });
  const { busy, error, run } = useAction();
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      const res = await api<{ token: string }>(
        "POST",
        mode === "login" ? "/api/auth/login" : "/api/auth/register",
        mode === "login" ? { email: form.email, password: form.password } : form,
      );
      setToken(res.token);
      onAuthed();
    });
  };

  return (
    <div className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Cardcore</h1>
        <p className="muted">Collection valuation &amp; insurance ledger</p>
        <label>
          Email
          <input type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
        </label>
        <label>
          Password
          <input type="password" required minLength={mode === "register" ? 10 : 1} value={form.password} onChange={set("password")} />
        </label>
        {mode === "register" && (
          <>
            <label>
              Display name
              <input required value={form.displayName} onChange={set("displayName")} />
            </label>
            <label>
              Base currency
              <input required pattern="[A-Z]{3}" value={form.baseCurrency} onChange={set("baseCurrency")} />
            </label>
          </>
        )}
        <ErrorNote error={error} />
        <button className="primary" disabled={busy}>
          {mode === "login" ? "Sign in" : "Create account"}
        </button>
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

/** One-time password reset from a link issued by an administrator (or an emailed link, once email is configured). */
export function ResetPassword({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const { busy, error, run } = useAction();
  return (
    <div className="auth">
      <form
        className="card auth-card"
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => {
            await api("POST", "/api/auth/password-reset/confirm", { token, newPassword: password });
            setDone(true);
          });
        }}
      >
        <h1>Reset password</h1>
        {done ? (
          <>
            <p>Your password has been changed.</p>
            <a href="#/dashboard">Sign in</a>
          </>
        ) : (
          <>
            <label>
              New password
              <input type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <ErrorNote error={error} />
            <button className="primary" disabled={busy}>
              Set password
            </button>
          </>
        )}
      </form>
    </div>
  );
}
