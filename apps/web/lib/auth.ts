export const ACCESS_TOKEN_STORAGE_KEY = "aim.access_token";

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
    return;
  }

  storage.setItem(ACCESS_TOKEN_STORAGE_KEY, normalizedAccessToken);
}

export function clearStoredAccessToken(
  storage: TokenStorage | null = getBrowserTokenStorage()
): void {
  storage?.removeItem(ACCESS_TOKEN_STORAGE_KEY);
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
