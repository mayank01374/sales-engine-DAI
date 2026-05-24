import { useState } from "react";
import { createRoot } from "react-dom/client";
import { Sidebar } from "./components/Sidebar";
import type { Page } from "./navigation";
import { DailyTriggers } from "./pages/DailyTriggers";
import { DiscoveryRuns } from "./pages/DiscoveryRuns";
import { Opportunities } from "./pages/Opportunities";
import { Settings } from "./pages/Settings";
import "./styles.css";

function App() {
  const [page, setPage] = useState<Page>("daily");
  return (
    <div className="app">
      <Sidebar page={page} onNavigate={setPage} />
      <main>
        {page === "daily" && <DailyTriggers onNavigate={setPage} />}
        {page === "runs" && <DiscoveryRuns />}
        {page === "opportunities" && <Opportunities />}
        {page === "settings" && <Settings />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
