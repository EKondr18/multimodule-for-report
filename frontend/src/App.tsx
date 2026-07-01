import { useState } from "react";
import { TABS } from "./tabs";

export default function App() {
  const [activeTab, setActiveTab] = useState(TABS[0].id);
  const active = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  return (
    <div className="app-shell">
      <nav className="tab-nav">
        <div className="tab-nav-header">
          <div className="tab-nav-logo">RMS</div>
          <div className="tab-nav-subtitle">Reporting Suite</div>
        </div>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={tab.id === activeTab ? "active" : ""}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <main className="tab-content">
        <active.Component />
      </main>
    </div>
  );
}
