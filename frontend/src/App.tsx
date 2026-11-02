import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { NewScan } from "./pages/NewScan";
import { Jobs } from "./pages/Jobs";
import { JobDetail } from "./pages/JobDetail";
import { Capabilities } from "./api/types";
import { fetchCapabilities } from "./api/client";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import { GuideProvider } from "./context/GuideContext";
import { UserGuideModal } from "./components/UserGuideModal";

const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"new" | "jobs" | "detail">("new");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const { theme } = useTheme();

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
    <div
      className={`min-h-screen flex flex-col font-sans transition-colors duration-200 ${
        theme === "dark" ? "bg-[#09090b] text-zinc-100" : "bg-slate-50 text-slate-900"
      }`}
    >
      <Header
        activeTab={activeTab === "detail" ? "jobs" : activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setSelectedJobId(null);
        }}
        capabilities={capabilities}
      />

      <main className="flex-1 pb-16">
        {activeTab === "new" && (
          <NewScan capabilities={capabilities} onJobCreated={handleJobCreated} />
        )}

        {activeTab === "jobs" && (
          <Jobs
            onSelectJob={handleSelectJob}
            onNewScan={() => setActiveTab("new")}
            capabilities={capabilities}
          />
        )}

        {activeTab === "detail" && selectedJobId && (
          <JobDetail jobId={selectedJobId} onBack={handleBackToJobs} />
        )}
      </main>

      <footer
        className={`border-t py-6 text-center text-xs transition-colors ${
          theme === "dark"
            ? "border-zinc-800/80 bg-zinc-950/60 text-zinc-500"
            : "border-slate-200 bg-white/60 text-slate-500"
        }`}
      >
        <p className="font-mono text-[11px]">
          ScanForge Studio — Self-Hostable Spatial 3D Reconstruction Platform
        </p>
      </footer>

      {/* Global Interactive Guide Modal */}
      <UserGuideModal />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <GuideProvider>
        <AppContent />
      </GuideProvider>
    </ThemeProvider>
  );
};

export default App;
