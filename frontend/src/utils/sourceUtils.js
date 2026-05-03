function cleanText(value) {
  return String(value || "").trim();
}

function stripWww(hostname) {
  return cleanText(hostname).replace(/^www\./i, "");
}

function hostFromUrl(url) {
  try {
    return stripWww(new URL(url).hostname);
  } catch {
    return "";
  }
}

function isGroundingRedirectHost(hostname) {
  return /(^|\.)vertexaisearch\.cloud\.google\.com$/i.test(cleanText(hostname))
    || /(^|\.)generativelanguage\.googleapis\.com$/i.test(cleanText(hostname));
}

function isDomainLike(value) {
  return /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(cleanText(value));
}

export function sourceDisplayLabel(source) {
  const title = cleanText(source?.title);
  const host = hostFromUrl(source?.url);

  if (title && !isDomainLike(title)) return title;
  if (title && isGroundingRedirectHost(host)) return stripWww(title);

  if (host) return host;

  if (title) return stripWww(title);
  return cleanText(source?.source) || "Uploaded source";
}

function sourceIdentity(source) {
  const label = sourceDisplayLabel(source).toLowerCase();
  if (label && label !== "source" && label !== "uploaded source") return label;

  const url = cleanText(source?.url).replace(/\/+$/, "").toLowerCase();
  if (url) return url;

  return cleanText(source?.source).toLowerCase() || label;
}

export function normalizeSources(sources) {
  const unique = new Map();

  for (const source of Array.isArray(sources) ? sources : []) {
    const key = sourceIdentity(source);
    if (!key || unique.has(key)) continue;
    unique.set(key, source);
  }

  return Array.from(unique.values());
}
