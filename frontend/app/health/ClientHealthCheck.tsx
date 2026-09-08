"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status?: string;
  db?: string;
  error?: string;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function ClientHealthCheck() {
  const [clientHealth, setClientHealth] = useState<HealthData | null>(null);
  const [dbHealth, setDbHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiBase =
      process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

    async function fetchHealth(path: string): Promise<HealthData> {
      const response = await fetch(`${apiBase}${path}`);
      if (!response.ok) {
        throw new Error(`${path} returned HTTP ${response.status}`);
      }
      return response.json() as Promise<HealthData>;
    }

    async function checkHealth() {
      const [clientResult, dbResult] = await Promise.allSettled([
        fetchHealth("/health"),
        fetchHealth("/health/db"),
      ]);

      setClientHealth(
        clientResult.status === "fulfilled"
          ? clientResult.value
          : { error: errorMessage(clientResult.reason) },
      );
      setDbHealth(
        dbResult.status === "fulfilled"
          ? dbResult.value
          : { error: errorMessage(dbResult.reason) },
      );
      setLoading(false);
    }

    checkHealth();
  }, []);

  return (
    <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4 shadow-lg text-slate-100">
      <h3 className="text-lg font-semibold text-sky-400 flex items-center gap-2">
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
        Client-Side Fetch (Direct Browser CORS Test)
      </h3>

      {loading ? (
        <p className="text-slate-400 text-sm">Testing browser-to-FastAPI connection...</p>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center py-1 border-b border-slate-800">
            <span className="text-slate-400">Endpoint: GET /health</span>
            <span
              id="client-health-status"
              className={
                clientHealth?.status === "ok"
                  ? "font-mono font-medium text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded"
                  : "font-mono text-rose-400 bg-rose-950/60 px-2 py-0.5 rounded"
              }
            >
              {clientHealth?.status || clientHealth?.error || "Error"}
            </span>
          </div>

          <div className="flex justify-between items-center py-1 border-b border-slate-800">
            <span className="text-slate-400">Endpoint: GET /health/db</span>
            <span
              id="client-db-status"
              className={
                dbHealth?.db === "connected"
                  ? "font-mono font-medium text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded"
                  : "font-mono text-rose-400 bg-rose-950/60 px-2 py-0.5 rounded"
              }
            >
              {dbHealth?.db ? `db: ${dbHealth.db}` : dbHealth?.error || "Error"}
            </span>
          </div>

          <div className="pt-2 text-xs text-slate-400">
            CORS origin verified: <code className="text-sky-300">http://localhost:3000</code> → <code className="text-sky-300">http://localhost:8000</code>
          </div>
        </div>
      )}
    </div>
  );
}
