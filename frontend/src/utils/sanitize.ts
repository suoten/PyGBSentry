/**
 * HTML sanitizer — wraps DOMPurify to prevent XSS when rendering HTML content.
 *
 * Use `sanitizeHtml()` for any v-html binding.  For plain text, prefer v-text
 * or {{ }} interpolation instead.
 */
import DOMPurify from 'dompurify'

/**
 * Sanitize an HTML string, allowing only safe inline tags (e.g. <code>, <strong>,
 * <em>, <br>).  Strips <script>, event handlers, and other dangerous content.
 */
export function sanitizeHtml(dirty: string | undefined | null): string {
  if (!dirty) return ''
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'code', 'pre', 'br', 'span', 'a', 'p', 'ul', 'ol', 'li'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style'],
    ALLOW_DATA_ATTR: false,
  })
}

export default sanitizeHtml
