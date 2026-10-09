import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { NewScan } from "./pages/NewScan";
import { Jobs } from "./pages/Jobs";
import { JobDetail } from "./pages/JobDetail";
import { Capabilities } from "./api/types";
import { fetchCapabilities } from "./api/client";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"new" | "jobs" | "detail">("new");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);

  useEffect(() => {
    fetchCapabilities()
      .then(setCapabilities)
      .catch((err) => console.error("Could not fetch capabilities", err));
  }, []);

  const handleJobCreated = (jobId: string) => {
    setSelectedJobId(jobId);
    setActiveTab("detail");
  };

  const handleSelectJob = (jobId: string) => {
    setSelectedJobId(jobId);
    setActiveTab("detail");
  };

  const handleBackToJobs = () => {
    setActiveTab("jobs");
    setSelectedJobId(null);
  };

  return (
    <div className="min-h-screen bg-dark-bg text-dark-text flex flex-col font-sans">
      <Header
        activeTab={activeTab === "detail" ? "jobs" : activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setSelectedJobId(null);
        }}
        capabilities={capabilities}
      />


      <main className="flex-1 pb-12">
        {activeTab === "new" && (
          <NewScan capabilities={capabilities} onJobCreated={handleJobCreated} />
        )}

        {activeTab === "jobs" && (
          <Jobs
            onSelectJob={handleSelectJob}
            onNewScan={() => setActiveTab("new")}
          />
        )}

        {activeTab === "detail" && selectedJobId && (
          <JobDetail jobId={selectedJobId} onBack={handleBackToJobs} />
        )}
      </main>

      <footer className="border-t border-dark-border py-6 text-center text-xs text-dark-muted">
        <p>ScanForge — Self-hostable 3D Reconstruction Platform for Interior Spaces</p>
      </footer>
    </div>
  );
};

export default App;
