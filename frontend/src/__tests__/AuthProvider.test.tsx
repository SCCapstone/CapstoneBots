/**
 * Unit Tests for AuthProvider Component
 *
 * Tests the authentication context: login, logout, hydration, and token persistence.
 */

import React from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "@/components/AuthProvider";

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: jest.fn((key: string) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

function TestConsumer() {
  const { token, hydrated, isAuthenticated, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="hydrated">{String(hydrated)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="token">{token || "null"}</span>
      <button onClick={() => login("test-jwt-token")}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

beforeEach(() => {
  localStorageMock.clear();
  jest.clearAllMocks();
});

describe("AuthProvider", () => {
  it("hydrates and starts unauthenticated", async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    // After hydration
    expect(screen.getByTestId("hydrated").textContent).toBe("true");
    expect(screen.getByTestId("authenticated").textContent).toBe("false");
    expect(screen.getByTestId("token").textContent).toBe("null");
  });

  it("login sets token and persists to localStorage", async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await userEvent.click(screen.getByText("Login"));

    expect(screen.getByTestId("authenticated").textContent).toBe("true");
    expect(screen.getByTestId("token").textContent).toBe("test-jwt-token");
    expect(localStorageMock.setItem).toHaveBeenCalledWith("auth_token", "test-jwt-token");
  });

  it("logout clears token and localStorage", async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await userEvent.click(screen.getByText("Login"));
    await userEvent.click(screen.getByText("Logout"));

    expect(screen.getByTestId("authenticated").textContent).toBe("false");
    expect(screen.getByTestId("token").textContent).toBe("null");
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("auth_token");
  });

  it("restores token from localStorage on mount", async () => {
    localStorageMock.getItem.mockReturnValueOnce("saved-token");

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    // After useEffect runs
    expect(screen.getByTestId("token").textContent).toBe("saved-token");
    expect(screen.getByTestId("authenticated").textContent).toBe("true");
  });
});
