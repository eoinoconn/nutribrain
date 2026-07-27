/**
 * snake_case <-> camelCase conversion helpers for the typed API client.
 *
 * The backend (FastAPI/Pydantic) emits/accepts snake_case JSON field names
 * (see `api/app/api/*.py`); this client's types use camelCase per
 * docs/style.md. These helpers do pure key renaming only — no business
 * logic, no value coercion beyond structural recursion.
 */

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) => char.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
}

function isPlainObject(value: unknown): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Recursively renames object keys from snake_case to camelCase. */
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
  return value as T;
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
