"use client";
import React from "react";

type Instance = { id: number; label: string; base_url: string; album_id: string; size_limit_bytes: number };
type Member = { id: number; user_id: number; label: string; album_id: string; size_limit_bytes: number };

type Group = { id: number; name: string; code: string; schedule_time: string; instances: Instance[]; members: Member[] };

type SessionResp = { authenticated: boolean; user?: { id: number; username: string } };

type StatsResp = { total_unique: number; instances: Array<{ id:number; label:string; present:number; missing:number; coverage:number }>};

type ProgressResp = { status: string; total: number; done: number; per_instance: Record<string, { missing:number; done:number }> };

export default function GroupClient({ initial }: { initial: Group }) {
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";
  const [group, setGroup] = React.useState<Group>(initial);
  const [session, setSession] = React.useState<SessionResp>({ authenticated: false });
  const [joining, setJoining] = React.useState(false);
  const [label, setLabel] = React.useState("");
  const [albumId, setAlbumId] = React.useState("");
  const [limit, setLimit] = React.useState(100);
  const [busySync, setBusySync] = React.useState(false);
  const [stats, setStats] = React.useState<StatsResp | null>(null);
  const [progress, setProgress] = React.useState<ProgressResp | null>(null);

  const load = React.useCallback(async () => {
    try {
      const sres = await fetch(`${base}/api/auth/session`, { credentials: "include" });
      const sdata = (await sres.json()) as SessionResp;
      setSession(sdata);
      const gres = await fetch(`${base}/api/groups/${group.id}`, { credentials: "include", cache: "no-store" });
      if (gres.ok) setGroup(await gres.json());
      const st = await fetch(`${base}/api/groups/${group.id}/stats`, { cache: "no-store" });
      if (st.ok) setStats(await st.json());
      const pr = await fetch(`${base}/api/groups/${group.id}/progress`, { cache: "no-store" });
      if (pr.ok) setProgress(await pr.json());
    } catch {}
  }, [base, group.id]);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [load]);

  const myMember = session.authenticated ? group.members.find((m) => m.user_id === session.user?.id) : undefined;

  const onJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setJoining(true);
    try {
      await fetch(`${base}/api/groups/${group.id}/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ label, album_id: albumId, size_limit_mb: limit }),
      });
      setLabel("");
      setAlbumId("");
      setLimit(100);
      await load();
    } finally {
      setJoining(false);
    }
  };

  const onLeave = async () => {
    await fetch(`${base}/api/groups/${group.id}/leave`, { method: "POST", credentials: "include" });
    await load();
  };

  const onTriggerSync = async () => {
    setBusySync(true);
    try {
      await fetch(`${base}/api/groups/${group.id}/sync`, { method: "POST" });
    } finally {
      setBusySync(false);
    }
  };

  const renderBars = () => {
    const per = progress?.per_instance || {};
    const rows = stats?.instances || [];
    return (
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        {rows.map((r) => {
          const p = per[String(r.id)] || { missing: r.missing, done: 0 };
          const pct = r.missing ? Math.min(100, Math.round(((p.done || 0) / r.missing) * 100)) : 100;
          return (
            <div key={r.id} className="rounded border border-neutral-800 p-3">
              <div className="mb-1 flex items-center justify-between text-sm">
                <span>{r.label}</span>
                <span className="text-neutral-400">{r.present}/{stats?.total_unique} present · {r.missing} missing</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded bg-neutral-800">
                <div className="h-2 bg-green-500" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="min-h-screen p-8">
      <main className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">{group.name}</h1>
          <a href="/" className="text-sm text-indigo-400 hover:text-indigo-300">
            Back
          </a>
        </div>
        <div className="mt-2 text-sm text-neutral-400">
          Code: <code className="rounded bg-neutral-800 px-1 py-0.5">{group.code}</code>
        </div>
        <div className="mt-1 text-sm text-neutral-400">Daily: {group.schedule_time}</div>

        {stats && (
          <section className="card mt-6">
            <div className="mb-2 text-sm text-neutral-400">Total unique assets: <span className="font-semibold text-neutral-200">{stats.total_unique}</span></div>
            {renderBars()}
          </section>
        )}

        <section className="card mt-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Members</h2>
            <div className="flex items-center gap-3">
              <button onClick={onTriggerSync} disabled={busySync} className="btn btn-primary">
                {busySync ? "Syncing…" : "Trigger Sync"}
              </button>
              {myMember ? (
                <button onClick={onLeave} className="btn btn-outline">Leave</button>
              ) : null}
            </div>
          </div>

          {group.members.length === 0 ? (
            <div className="text-neutral-400">No members yet.</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Album</th>
                    <th>Size Limit</th>
                  </tr>
                </thead>
                <tbody>
                  {group.members.map((m) => (
                    <tr key={m.id} className="hover:bg-neutral-900">
                      <td>{m.label}</td>
                      <td><code className="rounded bg-neutral-800 px-1 py-0.5 text-xs">{m.album_id}</code></td>
                      <td>{Math.floor(m.size_limit_bytes / (1024 * 1024))} MB</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {session.authenticated && !myMember && (
            <form onSubmit={onJoin} className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-4">
              <input className="input" placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} />
              <input className="input" placeholder="Album ID" value={albumId} onChange={(e) => setAlbumId(e.target.value)} required />
              <input className="input" type="number" min={1} placeholder="Limit MB" value={limit} onChange={(e) => setLimit(parseInt(e.target.value || "100"))} />
              <button disabled={joining} className="btn btn-primary" type="submit">{joining ? "Joining…" : "Join Group"}</button>
            </form>
          )}
        </section>

        {group.instances && group.instances.length > 0 && (
          <section className="card mt-6">
            <h2 className="mb-4 text-base font-semibold">Legacy Instances</h2>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Album</th>
                    <th>Size Limit</th>
                  </tr>
                </thead>
                <tbody>
                  {group.instances.map((i) => {
                    const baseUrl = i.base_url.endsWith("/api") ? i.base_url.slice(0, -4) : i.base_url;
                    const albumHref = `${baseUrl}/albums/${i.album_id}`;
                    return (
                      <tr key={i.id} className="hover:bg-neutral-900">
                        <td>{i.label}</td>
                        <td><a className="text-indigo-400 hover:text-indigo-300" href={albumHref} target="_blank" rel="noreferrer"><code className="rounded bg-neutral-800 px-1 py-0.5 text-xs">{i.album_id}</code></a></td>
                        <td>{Math.floor(i.size_limit_bytes / (1024 * 1024))} MB</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
