import { Database, FileSearch, Globe, Settings as SettingsIcon } from "lucide-react";
import type { Page } from "../navigation";

export function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (page: Page) => void }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="logo" src="/download.png" alt="DecoverAI logo" />
        <div className="brandText">
          <span>Sales Engine</span>
        </div>
      </div>
      <button className={page === "daily" ? "active" : ""} onClick={() => onNavigate("daily")}>
        <FileSearch size={18} />
        <span>Daily Triggers</span>
      </button>
      <button className={page === "runs" ? "active" : ""} onClick={() => onNavigate("runs")}>
        <Globe size={18} />
        <span>Discovery Runs</span>
      </button>
      <button className={page === "opportunities" ? "active" : ""} onClick={() => onNavigate("opportunities")}>
        <Database size={18} />
        <span>Opportunities</span>
      </button>
      <button className={page === "settings" ? "active" : ""} onClick={() => onNavigate("settings")}>
        <SettingsIcon size={18} />
        <span>Settings</span>
      </button>
    </aside>
  );
}
