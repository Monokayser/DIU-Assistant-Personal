import { useEffect, useState } from "react";

const COMPACT_VIEWPORT_QUERY = "(max-width: 680px)";

export function useCompactViewport() {
  const [isCompactViewport, setIsCompactViewport] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(COMPACT_VIEWPORT_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const mediaQuery = window.matchMedia(COMPACT_VIEWPORT_QUERY);
    const syncViewport = (event) => {
      setIsCompactViewport(event.matches);
    };

    setIsCompactViewport(mediaQuery.matches);

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", syncViewport);
      return () => mediaQuery.removeEventListener("change", syncViewport);
    }

    mediaQuery.addListener(syncViewport);
    return () => mediaQuery.removeListener(syncViewport);
  }, []);

  return isCompactViewport;
}
