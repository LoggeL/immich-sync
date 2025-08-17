import React from "react";
import { notFound } from "next/navigation";
import GroupClient from "./GroupClient";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

type Instance = { id: number; label: string; base_url: string; album_id: string; size_limit_bytes: number };
type Member = { id: number; user_id: number; label: string; album_id: string; size_limit_bytes: number };

type Group = { id: number; name: string; code: string; schedule_time: string; instances: Instance[]; members: Member[] };

export default async function GroupPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${BASE}/api/groups/${id}`, { cache: "no-store" });
  if (res.status === 404) return notFound();
  const data = (await res.json()) as Group;
  return <GroupClient initial={data} />;
}
