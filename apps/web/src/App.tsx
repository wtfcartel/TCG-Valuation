import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";
import { AuthPage } from "./pages/Auth";
import { Dashboard } from "./pages/Dashboard";
import { AddAsset } from "./pages/AddAsset";
import { AssetDetail } from "./pages/AssetDetail";
import { Insurance } from "./pages/Insurance";
import { Reports } from "./pages/Reports";

export type Route =
  | { name: "dashboard" }
  | { name: "add" }
  | { name: "asset"; id: string }
  | { name: "insurance" }
  | { name: "reports" };

export interface Me {
  id: string;
  email: string;
  display_name: string;
  role: string;
  base_currency: string;
  collections: Array<{ id: string; name: string; base_currency: string }>;
}

function parseHash(): Route {
  const [name, id] = location.hash.replace(/^#\/?/, "").split("/");
  if (name === "asset" && id) return { name: "asset", id };
  if (name === "add" || name === "insurance" || name === "reports") return { name };
  return { name: "dashboard" };
}

export function navigate(route: Route): void {
  location.hash = route.name === "asset" ? `/asset/${route.id}` : `/${route.name}`;
}

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [route, setRoute] = useState<Route>(parseHash());
  const [loading, setLoading] = useState(Boolean(getToken()));

  const loadMe = useCallback(async () => {
    if (!getToken()) return setLoading(false);
    try {
      setMe(await api<Me>("GET", "/api/me"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [loadMe]);

  if (loading) return <div className="center muted">Loading…</div>;
  if (!me) return <AuthPage onAuthed={loadMe} />;
  const collection = me.collections[0]!;

  const nav: Array<[Route["name"], string]> = [
    ["dashboard", "Portfolio"],
    ["add", "Add asset"],
    ["insurance", "Insurance"],
    ["reports", "Reports"],
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">Cardcore</div>
        <nav>
          {nav.map(([name, text]) => (
            <a key={name} href={`#/${name}`} className={route.name === name ? "active" : ""}>
              {text}
            </a>
          ))}
        </nav>
        <div className="who">
          <span className="muted">{me.display_name}</span>
          <button
            className="link"
            onClick={() => {
              setToken(null);
              setMe(null);
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main>
        {route.name === "dashboard" && <Dashboard collection={collection} />}
        {route.name === "add" && <AddAsset collection={collection} />}
        {route.name === "asset" && <AssetDetail id={route.id} currency={collection.base_currency} />}
        {route.name === "insurance" && <Insurance collection={collection} />}
        {route.name === "reports" && <Reports collection={collection} />}
      </main>
    </div>
  );
}
