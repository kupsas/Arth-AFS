/**
 * Labels for **bank transaction** uploads (subset of ``pipeline/detection.PARSER_LABELS``).
 * When you add a new upload parser, extend both that dict and this list.
 */
export const TRANSACTION_UPLOAD_TYPE_LABELS: readonly string[] = [
  "HDFC Savings Account Statement (.txt export)",
  "HDFC Combined Bank Statement (PDF)",
  "HDFC Credit Card Statement (.csv export)",
  "HDFC Credit Card Statement (PDF)",
  "ICICI Bank Savings Account Statement (PDF)",
]
