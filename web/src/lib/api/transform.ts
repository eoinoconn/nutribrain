/**
 * snake_case <-> camelCase conversion helpers for the typed API client.
 *
 * The backend (FastAPI/Pydantic) emits/accepts snake_case JSON field names
 * (see `api/app/api/*.py`); this client's types use camelCase per
 * docs/style.md. Key renaming is pure structural recursion, no business
 * logic.
 *
 * Value coercion (incoming only): Pydantic serializes `Decimal` fields
 * (all macro/quantity numbers, per docs/style.md's "Decimal in Python,
 * number in TS" rule) as JSON *strings*, e.g. `"protein_g": "15.0000"`, to
 * avoid float precision loss. This client's types declare those fields as
 * `number`, so `keysToCamel` also parses plain decimal-looking strings
 * into JS numbers on the way in. Non-numeric strings (dates, enums, names,
 * IANA tz names) never match the decimal pattern and pass through
 * unchanged. `keysToSnake` (outgoing requests) does no coercion — request
 * bodies are already built from real JS numbers, and Pydantic accepts a
 * bare JSON number for a `Decimal` field.
 */

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

const DECIMAL_STRING = /^-?\d+(\.\d+)?$/;

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) => char.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
}

function isPlainObject(value: unknown): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function coerceDecimalString(value: JsonValue): JsonValue {
  if (typeof value === "string" && DECIMAL_STRING.test(value)) {
    return Number(value);
  }
  return value;
}

/** Recursively renames object keys from snake_case to camelCase, coercing Decimal-as-string values to numbers. */
export function keysToCamel<T>(value: unknown): T {
  if (Array.isArray(value)) {
    return value.map((item) => keysToCamel(item)) as unknown as T;
  }
  if (isPlainObject(value)) {
    const result: Record<string, JsonValue> = {};
    for (const [key, val] of Object.entries(value)) {
      result[snakeToCamel(key)] = keysToCamel(val);
    }
    return result as unknown as T;
  }
  return coerceDecimalString(value as JsonValue) as T;
}

/** Recursively renames object keys from camelCase to snake_case. */
export function keysToSnake(value: unknown): JsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => keysToSnake(item));
  }
  if (isPlainObject(value)) {
    const result: Record<string, JsonValue> = {};
    for (const [key, val] of Object.entries(value)) {
      result[camelToSnake(key)] = keysToSnake(val);
    }
    return result;
  }
  return value as JsonValue;
}
