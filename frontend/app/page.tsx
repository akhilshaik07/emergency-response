import ClientHealthCheck from "./health/ClientHealthCheck";

export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center bg-slate-950 px-6 py-16 font-sans">
      <div className="w-full max-w-3xl space-y-8">
        <header className="space-y-3 text-center">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-sky-400">
            Community safety network
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Emergency Response Platform
          </h1>
          <p className="mx-auto max-w-xl text-base leading-7 text-slate-300">
            Coordinate residents, volunteers, security staff, and emergency
            contacts from one reliable response hub.
          </p>
        </header>
        <ClientHealthCheck />
      </div>
    </main>
  );
}
