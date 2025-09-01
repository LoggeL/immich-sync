"use client";
import React from "react";
import LoginRegister from "@/components/LoginRegister";
import { apiFetch } from "@/lib/api";

type Group = { id: number; label: string; owner_id: number; created_at: string };

export default function Home() {
  const [authenticated, setAuthenticated] = React.useState<boolean>(false);
  const [groups, setGroups] = React.useState<Group[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [creating, setCreating] = React.useState(false);
  const [newGroup, setNewGroup] = React.useState({ name: "", schedule_time: "02:00" });

  const load = React.useCallback(async () => {
    try {
      const gres = await apiFetch(`/api/groups`);
      if (gres.ok) {
        setAuthenticated(true);
        setGroups(await gres.json());
      } else {
        setAuthenticated(false);
      }
    } catch {
      setAuthenticated(false);
    }
    setLoading(false);
  }, [base]);

  React.useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="min-h-screen p-8">
        <main className="mx-auto max-w-7xl">
          <h1 className="text-2xl font-bold">Immich Sync</h1>
          <p className="mt-4 text-neutral-400">Loading…</p>
        </main>
      </div>
    );
  }

  if (!authenticated) {
    return <LoginRegister />;
  }

  const onLogout = async (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.removeItem("immich_sync_token");
    window.location.reload();
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await fetch(`${base}/api/groups`, { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: JSON.stringify(newGroup) });
      if (res.ok) {
        setNewGroup({ name: "", schedule_time: "02:00" });
        await load();
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen p-8">
      <main className="mx-auto max-w-7xl">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Immich Sync</h1>
          <form onSubmit={onLogout}>
            <button className="btn btn-outline" type="submit">Logout</button>
          </form>
        </div>
        <section className="card mt-6">
          <h2 className="mb-4 text-base font-semibold">Create Sync Group</h2>
          <form onSubmit={onCreate} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <input className="input" placeholder="Label" value={newGroup.name} onChange={(e)=>setNewGroup({...newGroup, name: e.target.value})} />
            <input className="input" placeholder="Expires (optional ISO)" value={newGroup.schedule_time} onChange={(e)=>setNewGroup({...newGroup, schedule_time: e.target.value})} />
            <button disabled={creating} className="btn btn-primary" type="submit">{creating ? "Creating…" : "Create"}</button>
          </form>
        </section>
        <p className="mt-6 text-neutral-400">Groups</p>
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <a key={g.id} href={`/groups/${g.id}`} className="card hover:bg-neutral-900">
              <div className="text-lg font-semibold">{g.label}</div>
              <div className="mt-1 text-xs text-neutral-400">Owner: {g.owner_id}</div>
            </a>
          ))}
          {groups.length === 0 && (
            <div className="text-neutral-400">No groups yet.</div>
          )}
        </div>
      </main>
    </div>
  );
}
