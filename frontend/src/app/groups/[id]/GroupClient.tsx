"use client";
import React from "react";
import { apiFetch } from "@/lib/api";

type Instance = { id: number; label: string; base_url: string; album_id: string; size_limit_bytes: number };
type Group = { id: number; label: string; instances: Instance[] };
type ProgressResp = { status: string; total: number; done: number; per_instance: Record<string, { missing:number; done:number }> };

export default function GroupClient({ initial }: { initial: Group }) {
  const [group, setGroup] = React.useState<Group>(initial);
  const [busySync, setBusySync] = React.useState(false);
  const [progress, setProgress] = React.useState<ProgressResp | null>(null);

  const load = React.useCallback(async () => {
    try {
      const gres = await apiFetch(`/api/groups/${group.id}`);
      if (gres.ok) setGroup(await gres.json());
      const pr = await apiFetch(`/api/groups/${group.id}/progress`);
      if (pr.ok) setProgress(await pr.json());
    } catch {}
  }, [group.id]);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [load]);

  const onAddInstance = async (e: React.FormEvent) => {
    e.preventDefault();
    const form = new FormData(e.target as HTMLFormElement);
    const payload = {
      sync_id: group.id,
      label: String(form.get("label") || ""),
      base_url: String(form.get("base_url") || ""),
      api_key: String(form.get("api_key") || ""),
      album_id: String(form.get("album_id") || ""),
      size_limit_bytes: Number(form.get("size_limit_bytes") || 104857600),
      active: true,
    };
    await apiFetch(`/api/instances`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    (e.target as HTMLFormElement).reset();
    await load();
  };

  const onTriggerSync = async () => {
    setBusySync(true);
    try {
      await apiFetch(`/api/groups/${group.id}/sync`, { method: "POST" });
    } finally {
      setBusySync(false);
    }
  };

  const renderBars = () => {
    const per = progress?.per_instance || {};
    const rows = group.instances.map((i) => ({ id: i.id, label: i.label, present: 0, missing: per[String(i.id)]?.missing ?? 0 }));
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
          <h1 className="text-2xl font-bold">{group.label}</h1>
          <a href="/" className="text-sm text-indigo-400 hover:text-indigo-300">
            Back
          </a>
        </div>
        <div className="mt-1 text-sm text-neutral-400">Instances: {group.instances.length}</div>

        <section className="card mt-6">
          <div className="mb-2 text-sm text-neutral-400">Progress</div>
          {renderBars()}
        </section>

        <section className="card mt-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Members</h2>
            <div className="flex items-center gap-3">
              <button onClick={onTriggerSync} disabled={busySync} className="btn btn-primary">
                {busySync ? "Syncing…" : "Trigger Sync"}
              </button>
              
            </div>
          </div>

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
                {group.instances.map((m) => (
                  <tr key={m.id} className="hover:bg-neutral-900">
                    <td>{m.label}</td>
                    <td><code className="rounded bg-neutral-800 px-1 py-0.5 text-xs">{m.album_id}</code></td>
                    <td>{Math.floor(m.size_limit_bytes / (1024 * 1024))} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <form onSubmit={onAddInstance} className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-6">
            <input name="label" className="input" placeholder="Label" />
            <input name="base_url" className="input" placeholder="Instance Base URL" />
            <input name="api_key" className="input" placeholder="API Key" />
            <input name="album_id" className="input" placeholder="Album ID" required />
            <input name="size_limit_bytes" type="number" className="input" placeholder="Limit bytes" defaultValue={100*1024*1024} />
            <button className="btn btn-primary" type="submit">Add Instance</button>
          </form>
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
