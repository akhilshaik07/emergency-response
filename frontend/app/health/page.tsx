import ClientHealthCheck from "./ClientHealthCheck";

export const dynamic = "force-dynamic";

async function getServerHealth() {
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${apiBase}/health`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err: any) {
    return { status: "error", error: err.message || "Failed server fetch" };
  }
}

export default async function HealthPage() {
  const serverHealth = await getServerHealth();

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            System Integration Health Check
          </h1>
          <p className="text-slate-400 text-sm">
            Emergency Response Platform: FastAPI + Next.js Integration Verification
          </p>
        </div>

        {/* Server-Side Fetch Section */}
        <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-3 shadow-lg">
          <h3 className="text-lg font-semibold text-emerald-400 flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
            Server-Side Component Fetch
          </h3>
          <div className="flex justify-between items-center py-1 text-sm border-b border-slate-800">
            <span className="text-slate-400">Endpoint: GET /health</span>
            <span
              id="server-health-status"
              className={
                serverHealth?.status === "ok"
                  ? "font-mono font-medium text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded"
                  : "font-mono text-rose-400 bg-rose-950/60 px-2 py-0.5 rounded"
              }
            >
              {serverHealth?.status || "error"}
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Rendered via Next.js Server Component without browser proxy.
          </p>
        </div>

        {/* Client-Side Fetch & CORS Test Section */}
        <ClientHealthCheck />
      </div>
    </main>
  );
}
