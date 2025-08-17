"use client";
import React from "react";

export default function LoginRegister() {
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState<any>({ username: "", password: "", confirm_password: "", instance_base_url: "", instance_api_key: "", captcha_answer: "" });
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";
  const onSubmit: React.FormEventHandler = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const url = mode === "login" ? `${base}/api/auth/login` : `${base}/api/auth/register`;
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form), credentials: "include" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Request failed");
      }
      window.location.reload();
    } catch (err: any) {
      setError(err.message || "Failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-h-screen p-8">
      <main className="mx-auto max-w-md">
        <h1 className="text-2xl font-bold">Immich Sync</h1>
        <div className="mt-4 flex gap-4 text-sm">
          <button className={`px-3 py-1 rounded ${mode === "login" ? "bg-indigo-600 text-white" : "bg-gray-100"}`} onClick={() => setMode("login")}>Login</button>
          <button className={`px-3 py-1 rounded ${mode === "register" ? "bg-indigo-600 text-white" : "bg-gray-100"}`} onClick={() => setMode("register")}>Register</button>
        </div>
        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        <form onSubmit={onSubmit} className="mt-4 grid grid-cols-1 gap-3">
          <input className="w-full rounded border p-2" placeholder="Username" value={form.username} onChange={(e)=>setForm({...form, username: e.target.value})} required />
          <input type="password" className="w-full rounded border p-2" placeholder="Password" value={form.password} onChange={(e)=>setForm({...form, password: e.target.value})} required />
          {mode === "register" && (
            <>
              <input type="password" className="w-full rounded border p-2" placeholder="Confirm Password" value={form.confirm_password} onChange={(e)=>setForm({...form, confirm_password: e.target.value})} required />
              <input className="w-full rounded border p-2" placeholder="Instance Base URL (https://...)" value={form.instance_base_url} onChange={(e)=>setForm({...form, instance_base_url: e.target.value})} required />
              <input className="w-full rounded border p-2" placeholder="Instance API Key" value={form.instance_api_key} onChange={(e)=>setForm({...form, instance_api_key: e.target.value})} required />
              <input className="w-full rounded border p-2" placeholder="Captcha: What is 2 + 3?" value={form.captcha_answer} onChange={(e)=>setForm({...form, captcha_answer: e.target.value})} required />
            </>
          )}
          <button disabled={busy} className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50" type="submit">{busy ? "Please wait…" : (mode === "login" ? "Login" : "Register")}</button>
        </form>
      </main>
    </div>
  );
}
