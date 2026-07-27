/**
 * Token gate (T-070): renders the paste-token landing screen when no
 * token is stored, and the full app once a token is present. Listens for
 * `TOKEN_CLEARED_EVENT` so a 401 anywhere in the app (via apiClient) drops
 * the user back to this screen with an "invalid token" message.
 */

import { useCallback, useEffect, useState } from "react";
import {
  TOKEN_CLEARED_EVENT,
  type TokenClearedDetail,
  getToken,
  setToken
} from "../lib/tokenStore";

interface TokenGateProps {
  children: React.ReactNode;
}

export default function TokenGate({ children }: TokenGateProps): JSX.Element {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);

  useEffect(() => {
    function handleCleared(event: Event): void {
      const detail = (event as CustomEvent<TokenClearedDetail>).detail;
      setTokenState(null);
      if (detail?.reason === "invalid") {
        setInvalidMessage("Your token was rejected by the server. Please paste a valid token.");
      }
    }
    window.addEventListener(TOKEN_CLEARED_EVENT, handleCleared);
    return () => window.removeEventListener(TOKEN_CLEARED_EVENT, handleCleared);
  }, []);

  const handleSubmit = useCallback((newToken: string) => {
    setToken(newToken);
    setTokenState(newToken);
    setInvalidMessage(null);
  }, []);

  if (!token) {
    return <TokenPasteScreen onSubmit={handleSubmit} invalidMessage={invalidMessage} />;
  }

  return <>{children}</>;
}

interface TokenPasteScreenProps {
  onSubmit: (token: string) => void;
  invalidMessage: string | null;
}

function TokenPasteScreen({ onSubmit, invalidMessage }: TokenPasteScreenProps): JSX.Element {
  const [value, setValue] = useState("");
  const [touched, setTouched] = useState(false);

  const trimmed = value.trim();
  const showRequiredError = touched && trimmed.length === 0;

  function handleSubmitForm(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setTouched(true);
    if (trimmed.length === 0) {
      return;
    }
    onSubmit(trimmed);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 p-6 shadow-sm dark:border-slate-800">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">NutriBrain</h1>
          <p className="text-sm text-slate-700 dark:text-slate-300">Paste your API token to continue.</p>
        </div>

        {invalidMessage ? (
          <p
            role="alert"
            className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {invalidMessage}
          </p>
        ) : null}

        <form className="space-y-3" onSubmit={handleSubmitForm} noValidate>
          <div className="space-y-1">
            <label className="block text-sm font-medium" htmlFor="api-token">
              API token
            </label>
            <input
              id="api-token"
              name="api-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              aria-invalid={showRequiredError}
              aria-describedby={showRequiredError ? "api-token-error" : undefined}
            />
            {showRequiredError ? (
              <p id="api-token-error" className="text-sm text-red-700 dark:text-red-300">
                A token is required.
              </p>
            ) : null}
          </div>

          <button
            type="submit"
            className="w-full rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2"
          >
            Continue
          </button>
        </form>
      </div>
    </main>
  );
}
