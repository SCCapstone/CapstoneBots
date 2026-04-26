import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider, useAuth } from "@/components/AuthProvider";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] ?? null),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key];
    }),
    clear: jest.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, "localStorage", { value: localStorageMock });

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(payload));
  return `${header}.${body}.sig`;
}

function makeToken(secondsFromNow: number): string {
  const exp = Math.floor(Date.now() / 1000) + secondsFromNow;
  return fakeJwt({ sub: "auth@test.com", exp });
}

function TestConsumer() {
  const { login, token, isAuthenticated } = useAuth();

  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="token">{token ?? "null"}</span>
      <button onClick={() => login(makeToken(60))}>Login short-lived token</button>
    </div>
  );
}

describe("AuthProvider refresh behavior", () => {
  let user: ReturnType<typeof userEvent.setup>;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    localStorageMock.clear();
    global.fetch = jest.fn();
    user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("logs out when refresh endpoint returns unauthorized", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "expired" }),
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /login short-lived token/i }));

    await act(async () => {
      jest.runOnlyPendingTimers();
    });

    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("false");
      expect(screen.getByTestId("token").textContent).toBe("null");
    });

    expect(localStorageMock.removeItem).toHaveBeenCalledWith("auth_token");
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps user logged in and retries after a transient network failure", async () => {
    const refreshedToken = makeToken(3600);
    (global.fetch as jest.Mock)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: refreshedToken }),
      });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /login short-lived token/i }));

    await act(async () => {
      jest.runOnlyPendingTimers();
    });

    expect(screen.getByTestId("authenticated").textContent).toBe("true");
    expect(localStorageMock.removeItem).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });

    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("true");
      expect(screen.getByTestId("token").textContent).toBe(refreshedToken);
    });

    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
