const TIMEZONE_SUFFIX_RE = /([zZ]|[+-]\d{2}:\d{2})$/;

export function parseApiDateTime(dateString: string): Date {
  const normalized = TIMEZONE_SUFFIX_RE.test(dateString)
    ? dateString
    : `${dateString}Z`;

  return new Date(normalized);
}

export function formatApiDateTime(dateString: string): string {
  const date = parseApiDateTime(dateString);
  return Number.isNaN(date.getTime()) ? dateString : date.toLocaleString();
}

export function formatApiDate(dateString: string): string {
  const date = parseApiDateTime(dateString);
  return Number.isNaN(date.getTime()) ? dateString : date.toLocaleDateString();
}
