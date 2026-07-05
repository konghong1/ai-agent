/**
 * Media URL Proxy Utility
 *
 * Converts external CDN URLs to backend proxy URLs to avoid
 * client-side proxy/network restrictions (e.g. ERR_PROXY_CONNECTION_FAILED).
 */

// Domains that must be routed through the backend proxy
const PROXY_DOMAINS = [
  "platform-outputs.agnes-ai.space",
  // Add other CDN domains here as needed
]

/**
 * Convert an external CDN URL to a backend proxy URL.
 * Relative URLs (e.g. "/api/...") are returned as-is.
 */
export function proxyMediaUrl(url: string | undefined | null): string {
  if (!url) return ""

  // Already a relative path or proxy URL — return as-is
  if (url.startsWith("/api/")) return url

  try {
    const parsed = new URL(url)
    // Check if the hostname matches any proxy domain
    if (PROXY_DOMAINS.some(
      (domain) => parsed.hostname === domain || parsed.hostname.endsWith("." + domain)
    )) {
      return `/api/media/proxy?url=${encodeURIComponent(url)}`
    }
  } catch {
    // Not a valid URL — return as-is
  }

  return url
}
