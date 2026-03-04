import en from "../locales/en.json";

/**
 * Look up a dot-separated key in the English locale and optionally
 * interpolate {varName} placeholders.
 *
 * Returns the key itself when the path doesn't resolve to a string.
 */
export function t(key: string, vars?: Record<string, string>): string {
  const parts = key.split(".");
  let current: unknown = en;

  for (const part of parts) {
    if (typeof current !== "object" || current === null) return key;
    current = (current as Record<string, unknown>)[part];
  }

  if (typeof current !== "string") return key;

  let value = current;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replace(`{${k}}`, v);
    }
  }

  return value;
}
