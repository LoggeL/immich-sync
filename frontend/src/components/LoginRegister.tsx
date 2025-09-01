"use client";
import React from "react";

import { API_BASE, setToken } from "@/lib/api";

export default function LoginRegister() {
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState<any>({ username: "", password: "" });
  const onSubmit: React.FormEventHandler = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        const r = await fetch(`${API_BASE}/api/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
        if (!r.ok) throw new Error("Registration failed");
      }
      const res = await fetch(`${API_BASE}/api/auth/login_json`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      if (!res.ok) throw new Error("Login failed");
      const data = await res.json();
      setToken(data.access_token);
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
          {mode === "register" && null}
          <button disabled={busy} className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50" type="submit">{busy ? "Please wait…" : (mode === "login" ? "Login" : "Register")}</button>
        </form>
      </main>
    </div>
  );
}
