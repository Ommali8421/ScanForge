import React, { createContext, useContext, useEffect, useState } from "react";

interface GuideContextType {
  guideEnabled: boolean;
  setGuideEnabled: (enabled: boolean) => void;
  toggleGuide: () => void;
  guideModalOpen: boolean;
  activeGuideTab: number;
  setActiveGuideTab: (tab: number) => void;
  openGuideModal: (initialTab?: number) => void;
  closeGuideModal: () => void;
}

const GuideContext = createContext<GuideContextType | undefined>(undefined);

const GUIDE_STORAGE_KEY = "scanforge_guide_enabled";

export const GuideProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [guideEnabled, setGuideEnabledState] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(GUIDE_STORAGE_KEY);
      if (stored !== null) {
        return stored === "true";
      }
    }
    return true; // Default to ON for new users
  });

  const [guideModalOpen, setGuideModalOpen] = useState(false);
  const [activeGuideTab, setActiveGuideTab] = useState(1);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(GUIDE_STORAGE_KEY, String(guideEnabled));
    }
  }, [guideEnabled]);

  const setGuideEnabled = (enabled: boolean) => {
    setGuideEnabledState(enabled);
  };

  const toggleGuide = () => {
    setGuideEnabledState((prev) => !prev);
  };

  const openGuideModal = (initialTab?: number) => {
    if (initialTab !== undefined && initialTab >= 1 && initialTab <= 5) {
      setActiveGuideTab(initialTab);
    }
    setGuideModalOpen(true);
  };

  const closeGuideModal = () => {
    setGuideModalOpen(false);
  };

  return (
    <GuideContext.Provider
      value={{
        guideEnabled,
        setGuideEnabled,
        toggleGuide,
        guideModalOpen,
        activeGuideTab,
        setActiveGuideTab,
        openGuideModal,
        closeGuideModal,
      }}
    >
      {children}
    </GuideContext.Provider>
  );
};

export const useGuide = (): GuideContextType => {
  const context = useContext(GuideContext);
  if (!context) {
    throw new Error("useGuide must be used within a GuideProvider");
  }
  return context;
};
