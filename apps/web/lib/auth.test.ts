import { describe, expect, it } from "vitest";
import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearStoredAccessToken,
  getStoredAccessToken,
  storeAccessToken
} from "./auth";

function createTokenStorage() {
  const values = new Map<string, string>();

  return {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    }
  };
}

describe("access token storage", () => {
  it("stores and reads a normalized access token", () => {
    const storage = createTokenStorage();

    storeAccessToken(" token ", storage);

    expect(getStoredAccessToken(storage)).toBe("token");
    expect(storage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("token");
  });

  it("clears an empty access token", () => {
    const storage = createTokenStorage();

    storeAccessToken("token", storage);
    storeAccessToken("   ", storage);

    expect(getStoredAccessToken(storage)).toBeNull();
  });

  it("clears the stored access token", () => {
    const storage = createTokenStorage();

    storeAccessToken("token", storage);
    clearStoredAccessToken(storage);

    expect(getStoredAccessToken(storage)).toBeNull();
  });

  it("returns null when browser storage is unavailable", () => {
    expect(getStoredAccessToken(null)).toBeNull();
  });
});
