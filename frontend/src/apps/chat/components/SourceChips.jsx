import React from "react";
import { Search } from "lucide-react";

export function SourceChips({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="source-chips">
      {sources.map((source, idx) => (
        <a
          key={idx}
          className="source-chip"
          href={source.url || "#"}
          target="_blank"
          rel="noreferrer"
          title={source.title}
        >
          <Search size={10} />
          <span className="source-chip-label">
            {source.title || `Source ${idx + 1}`}
          </span>
        </a>
      ))}
    </div>
  );
}
