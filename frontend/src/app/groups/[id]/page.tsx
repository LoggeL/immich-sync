import React from "react";
import { notFound } from "next/navigation";
import { API_BASE } from "@/lib/api";
import GroupClient from "./GroupClient";

const BASE = API_BASE;

type Instance = { id: number; label: string; base_url: string; album_id: string; size_limit_bytes: number };
type Group = { id: number; label: string; instances: Instance[] };

export default async function GroupPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${BASE}/api/groups/${id}`, { cache: "no-store" });
  if (res.status === 404) return notFound();
  const data = (await res.json()) as Group;
  return <GroupClient initial={data} />;
}
