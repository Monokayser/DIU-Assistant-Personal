export function resolveApiBase(
  rawValue,
  locationOrigin = typeof window !== "undefined" ? window.location.origin : "",
  locationHostname = typeof window !== "undefined" ? window.location.hostname : "",
) {
  const value = String(rawValue || "").trim().replace(/\/+$/, "");
  if (!locationOrigin) return value;
  const pageHost = String(locationHostname || "").toLowerCase();
  const isPageLocal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/.test(pageHost);

  if (!value) {
    if (!isPageLocal) return "";
    const fallbackHost = pageHost === "0.0.0.0" ? "127.0.0.1" : (pageHost || "127.0.0.1");
    return `http://${fallbackHost}:8765`;
  }

  try {
    const apiUrl = new URL(value, locationOrigin);
    const apiHost = apiUrl.hostname.toLowerCase();
    const isDevOnlyHost = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(apiHost);

    if (isDevOnlyHost && !isPageLocal && apiHost !== pageHost) {
      return "";
    }

    return apiUrl.origin === locationOrigin ? "" : apiUrl.origin;
  } catch {
    return "";
  }
}
