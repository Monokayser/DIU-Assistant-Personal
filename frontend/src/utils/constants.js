export const ASSISTANT_MODE = "assistant";
export const ASSISTANT_MODES = [
  {
    key: "assistant",
    label: "General",
    shortLabel: "General",
    description: "General DIU information",
    instruction: "",
    placeholder: "Message...",
  },
  {
    key: "admission",
    label: "Admission",
    shortLabel: "Admission",
    description: "Expert guidance",
    instruction: "AGENT ROLE: ADMISSION SPECIALIST. You are a DIU admission assistant. Provide specific, authoritative guidance on admissions, eligibility, and applications. If the user asks about unrelated topics, politely guide them back to admission matters.",
    placeholder: "Message...",
  },
  {
    key: "course",
    label: "Courses",
    shortLabel: "Courses",
    description: "Academic roadmaps",
    instruction: "AGENT ROLE: COURSE SPECIALIST. You are an academic assistant. Provide deep insights into program structures, curricula, and credit requirements. If the user asks about unrelated topics, politely guide them back to academic planning.",
    placeholder: "Message...",
  },
  {
    key: "scholarship",
    label: "Scholarship",
    shortLabel: "Scholarship",
    description: "Waiver calculators",
    instruction: "AGENT ROLE: SCHOLARSHIP SPECIALIST. You are a scholarship assistant for DIU financial aid and waivers. Provide precise calculations and eligibility details for scholarships. If the user asks about unrelated topics, politely guide them back to financial matters.",
    placeholder: "Message...",
  },
];
function resolveDirectUploadLimit() {
  if (typeof window === "undefined") {
    return 4 * 1024 * 1024;
  }

  const host = String(window.location.hostname || "").toLowerCase();
  const isLocal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(host);
  return isLocal ? 100 * 1024 * 1024 : 25 * 1024 * 1024;
}

export const MAX_DIRECT_UPLOAD_BYTES = resolveDirectUploadLimit();
export const SUPPORTED_UPLOAD_ACCEPT = [
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".xlsm",
  ".csv",
  ".tsv",
  ".ppt",
  ".pptx",
  ".txt",
  ".md",
  ".json",
  ".html",
  ".htm",
  ".rtf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".heic",
  ".heif",
  ".avif",
  ".mp3",
  ".wav",
  ".m4a",
  ".aac",
  ".ogg",
  ".flac",
  ".mp4",
  ".mpeg",
  ".mov",
  ".avi",
  ".webm",
  ".wmv",
  ".mpg",
  ".flv",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".py",
  ".java",
  ".cpp",
  ".c",
  ".cs",
  ".php",
  ".rb",
  ".go",
  ".rs",
  ".swift",
  ".kt",
  ".sql",
  ".xml",
  ".yaml",
  ".yml",
  ".log",
].join(",");
export const VOICE_LISTENING_STATUS = "Listening... tap the mic again to finish.";
export const VOICE_TRANSCRIBING_STATUS = "Transcribing voice...";
export const VOICE_DRAFT_READY_STATUS = "Voice draft ready. Review and send.";
export const VOICE_BAR_HEIGHTS = [8, 14, 20, 12, 24, 16, 28, 18, 22, 12, 18, 10];
