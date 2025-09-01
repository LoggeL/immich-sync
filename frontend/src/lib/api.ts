export type Token = { access_token: string; token_type: string };
export type UserOut = { id: number; username: string; created_at: string; base_url?: string | null };
export type GroupOut = { id: number; label: string; owner_id: number; active: boolean; expires_at: string | null; created_at: string };
export type InstanceOut = { id: number; user_id: number; sync_id: number; album_id: string; size_limit_bytes: number; active: boolean; username: string; base_url?: string | null };
export type GroupDetailOut = GroupOut & { instances: InstanceOut[], members: UserOut[] };
export type SyncProgress = {
  status: string;
  total: number;
  done: number;
  per_instance: Record<string, { missing: number; done: number; already: number }>;
  oversized: Record<string, any[]>;
  already?: number | null;
  remaining?: number | null;
  started_at?: string | null;
  eta_seconds?: number | null;
};
export type ImmichSettings = { base_url: string; api_key: string };
export type InstanceStats = { instance_id: number; album_id: string; album_title?: string | null; asset_count: number };

const API_BASE = import.meta.env.VITE_API_BASE || ""; // proxy handles /api

function getAuthHeader(): HeadersInit {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async register(username: string, password: string): Promise<UserOut> {
    return http<UserOut>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  async login(username: string, password: string): Promise<Token> {
    const token = await http<Token>("/api/auth/login_json", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    localStorage.setItem("token", token.access_token);
    return token;
  },
  async me(): Promise<UserOut> {
    return http<UserOut>("/api/me", { headers: { ...getAuthHeader() } });
  },
  async getImmichSettings(): Promise<ImmichSettings> {
    return http<ImmichSettings>("/api/settings/immich", { headers: { ...getAuthHeader() } });
  },
  async setImmichSettings(payload: ImmichSettings): Promise<ImmichSettings> {
    return http<ImmichSettings>("/api/settings/immich", {
      method: "POST",
      headers: { ...getAuthHeader() },
      body: JSON.stringify(payload),
    });
  },
  async listGroups(): Promise<GroupOut[]> {
    return http<GroupOut[]>("/api/groups", { headers: { ...getAuthHeader() } });
  },
  async createGroup(label: string, expires_at: string): Promise<GroupOut> {
    return http<GroupOut>("/api/groups", {
      method: "POST",
      headers: { ...getAuthHeader() },
      body: JSON.stringify({ label, expires_at }),
    });
  },
  async updateGroup(id: number, body: Partial<{ label: string; expires_at: string }>): Promise<GroupOut> {
    return http<GroupOut>(`/api/groups/${id}`, { method: 'PATCH', headers: { ...getAuthHeader() }, body: JSON.stringify(body) });
  },
  async getGroup(id: number): Promise<GroupDetailOut> {
    return http<GroupDetailOut>(`/api/groups/${id}`, { headers: { ...getAuthHeader() } });
  },
  async addMemberByUsername(groupId: number, username: string): Promise<{ status: string }> {
    return http<{ status: string }>(`/api/groups/${groupId}/members`, { method: 'POST', headers: { ...getAuthHeader() }, body: JSON.stringify({ username }) });
  },
  async removeMember(groupId: number, userId: number): Promise<{ status: string }> {
    return http<{ status: string }>(`/api/groups/${groupId}/members/${userId}`, { method: 'DELETE', headers: { ...getAuthHeader() } });
  },
  async addInstance(instance: { sync_id: number; album_id: string; size_limit_bytes?: number; active?: boolean }): Promise<InstanceOut> {
    return http<InstanceOut>("/api/instances", {
      method: "POST",
      headers: { ...getAuthHeader() },
      body: JSON.stringify(instance),
    });
  },
  async listInstances(): Promise<InstanceOut[]> {
    return http<InstanceOut[]>("/api/instances", { headers: { ...getAuthHeader() } });
  },
  async triggerSync(groupId: number): Promise<{ status: string }> {
    return http<{ status: string }>(`/api/groups/${groupId}/sync`, {
      method: "POST",
      headers: { ...getAuthHeader() },
    });
  },
  async getProgress(groupId: number): Promise<SyncProgress> {
    return http<SyncProgress>(`/api/groups/${groupId}/progress`, { headers: { ...getAuthHeader() } });
  },
  async getInstanceStats(groupId: number): Promise<InstanceStats[]> {
    return http<InstanceStats[]>(`/api/groups/${groupId}/instance_stats`, { headers: { ...getAuthHeader() } });
  },
};


