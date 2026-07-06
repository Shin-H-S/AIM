export const ACCESS_TOKEN_STORAGE_KEY = "aim.access_token";
export const ACCESS_TOKEN_CHANGE_EVENT = "aim:access-token-changed";

type TokenStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function getStoredAccessToken(
  storage: TokenStorage | null = getBrowserTokenStorage()
): string | null {
  if (!storage) {
    return null;
  }

  const accessToken = storage.getItem(ACCESS_TOKEN_STORAGE_KEY)?.trim();
  return accessToken ? accessToken : null;
}

export function storeAccessToken(
  accessToken: string,
  storage: TokenStorage | null = getBrowserTokenStorage()
): void {
  if (!storage) {
    return;
  }

  const normalizedAccessToken = accessToken.trim();
  if (!normalizedAccessToken) {
    storage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    notifyAccessTokenChange();
    return;
  }

  storage.setItem(ACCESS_TOKEN_STORAGE_KEY, normalizedAccessToken);
  notifyAccessTokenChange();
}

export function clearStoredAccessToken(
  storage: TokenStorage | null = getBrowserTokenStorage()
): void {
  storage?.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  notifyAccessTokenChange();
}

export function clearStoredAccessTokenIfMatches(
  accessToken: string,
  storage: TokenStorage | null = getBrowserTokenStorage()
): void {
  if (getStoredAccessToken(storage) !== accessToken.trim()) {
    return;
  }

  clearStoredAccessToken(storage);
}

// AppHeader listens for this event so login/logout in the same tab updates
// the session UI without a full page reload.
function notifyAccessTokenChange(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new Event(ACCESS_TOKEN_CHANGE_EVENT));
}

function getBrowserTokenStorage(): TokenStorage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
