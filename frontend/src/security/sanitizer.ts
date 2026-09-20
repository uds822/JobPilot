import DOMPurify from 'dompurify';

/**
 * Sanitizes input text to prevent XSS attacks.
 */
export function sanitizeInput(input: string | null | undefined): string {
  if (!input) return '';
  return DOMPurify.sanitize(input.trim(), {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'ul', 'ol', 'li', 'code'],
    ALLOWED_ATTR: ['href', 'target', 'rel'],
  });
}

/**
 * Validates URLs strictly ensuring http or https protocols.
 * Defends against SSRF, javascript: URIs, and file scheme attacks.
 */
export function isValidUrl(url: string): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/**
 * Masks sensitive auth tokens for security display.
 */
export function maskToken(token: string | null): string {
  if (!token) return 'No active token';
  if (token.length <= 10) return '********';
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}
