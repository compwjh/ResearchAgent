// Sensitive-value redaction for the Ollama Insights detail view.
//
// Two layers, both case-insensitive:
//    1. KEY matching (`redactSensitiveKey`): a key whose normalized name
//       contains a sensitive fragment is redacted entirely. Normalizing
//       `[-_ ]` → `` and lowercasing means bare words (`token`, `secret`,
//       `password`, `credential`, `apikey`, `accesskey`, `publickey`,
//       `authorization`, `bearer`, `cookie`) and underscored env-var forms
//       such as `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`,
//       `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` are all covered by the
//       same fragment list, while business keys like `model` / `route` /
//       `content` / `input` / `output` / `metadata` never match.
//    2. VALUE scrubbing (`redactSensitiveText`): inside free-form string
//       values, Langfuse-style keys that start with `sk-` / `pk-`
//       (e.g. `sk-lf-…`, `pk-lf-…`) and `Bearer <token>` pairs are masked so
//       an embedded credential cannot leak through the detail view.

/**
 * Sensitive key fragments. Underscores/hyphens in the key are normalized to
 * spaces first, so `AWS_ACCESS_KEY` becomes `aws access key` and the patterns
 * below match on word boundaries. `token` / `secret` are word-boundaried so
 * business fields like `tokens_per_sec` (→ `tokens per sec`) are NOT matched.
 */
const SENSITIVE_KEY_PATTERN = new RegExp(
  [
      "\\bauthorization\\b",
      "\\bbearer\\b",
      "\\bcookie\\b",
      "\\bcredential",
      "\\bpasswd\\b",
      // token/secret/credential must end the "word" so `tokens_per_sec`
      // (`tokens per sec`) and `secretive` are not matched.
      "\\btoken(?!\\w)",
      "\\bsecret(?!\\w)",
      "\\bpassword(?!\\w)",
      "\\baccesskey\\b",
      "\\bpublickey\\b",
      "\\bapikey\\b",
      "\\bsecretkey\\b",
      "\\btokenkey\\b",
      "\\baccesskeyid\\b",
      // `key` on its own boundary catches `API_KEY`, `AWS_ACCESS_KEY_ID`,
      // `LANGFUSE_PUBLIC_KEY`, `secret_key`, … (`api_key` → `api key`).
      "\\bkey\\b",
      ].join("|"),
     "i",
);

/**
 * Returns true when `key` names a sensitive field / environment variable.
 * Case-insensitive; covers both bare words and `*_X*` env-var forms while
 * leaving business fields such as `model` / `route` / `content` /
 * `tokens_per_sec` untouched.
 */
export function isSensitiveKey(key: string): boolean {
  const normalized = key.toLowerCase().replace(/[-_]/g, " ");
  return SENSITIVE_KEY_PATTERN.test(normalized);
}

/** Matches Langfuse-style key values such as `sk-lf-…` / `pk-lf-…` (and bare `sk-…` / `pk-…`). */
const langfuseKeyPattern = /(?:sk|pk)(?:-lf)?-[A-Za-z0-9._~+/=-]{6,}/g;

/**
 * Masks embedded credentials inside a single string value:
 *   - Langfuse-style `sk-…` / `pk-…` key values
 *   - `Bearer <token>` authorization pairs
 */
export function redactSensitiveText(value: string) {
  return value
     .replace(langfuseKeyPattern, "[REDACTED]")
     .replace(/(\bBearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[REDACTED]");
}

/**
 * Recursively redacts a detail payload.
 *   - objects: a sensitive *key* becomes `[REDACTED]`, otherwise recurse into the value.
 *   - arrays: recurse into each item.
 *   - strings: scrub embedded credentials.
 * Business fields (model, route, content, …) pass through untouched.
 */
export function redactSensitiveValue(value: unknown, key?: string): unknown {
  if (key !== undefined && isSensitiveKey(key)) return "[REDACTED]";
  if (typeof value === "string") return redactSensitiveText(value);
  if (Array.isArray(value)) {
    return value.map((item) => redactSensitiveValue(item));
    }
  if (value && typeof value === "object") {
    return Object.fromEntries(
     Object.entries(value).map(([entryKey, entryValue]) => [
       entryKey,
       redactSensitiveValue(entryValue, entryKey),
      ]),
     );
   }
  return value;
}

/**
 * Renders a detail payload for display: redacts sensitive values first,
 * then stringifies objects / leaves non-empty strings as-is.
 */
export function formatDetailValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "No data available.";
    }
  const redacted = redactSensitiveValue(value);
  if (typeof redacted === "string") return redacted;
  try {
    return JSON.stringify(redacted, null, 2) ?? "No data available.";
    } catch {
    return "Unable to render this value.";
    }
}
