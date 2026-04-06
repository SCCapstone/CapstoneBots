/**
 * Behavioral / UI Tests for Login Page
 *
 * Simulates user interactions: filling the form, submitting, and handling errors.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ============== Mocks ==============

// Mock next/navigation
const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
}));

// Mock AuthProvider
const mockLogin = jest.fn();
jest.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    token: null,
    hydrated: true,
    isAuthenticated: false,
    login: mockLogin,
    logout: jest.fn(),
  }),
}));

// Mock auth API
const mockLoginApi = jest.fn();
const mockResendVerificationApi = jest.fn();
jest.mock("@/lib/authApi", () => ({
  loginApi: (...args: unknown[]) => mockLoginApi(...args),
  resendVerificationApi: (...args: unknown[]) => mockResendVerificationApi(...args),
  ApiError: class ApiError extends Error {
    status: number;
    code: string | undefined;
    constructor(message: string, status: number, code?: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
    }
  },
}));

import LoginPage from "@/app/login/page";

beforeEach(() => {
  jest.clearAllMocks();
});

describe("LoginPage", () => {
  it("renders email and password fields", () => {
    render(<LoginPage />);

    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
  });

  it("renders Log In button", () => {
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /log in/i })).toBeInTheDocument();
  });

  it("renders sign up link", () => {
    render(<LoginPage />);
    expect(screen.getByText(/sign up/i)).toBeInTheDocument();
  });

  it("renders Blender Collab branding", () => {
    render(<LoginPage />);
    expect(screen.getByText("Blender Collab")).toBeInTheDocument();
  });

  it("calls loginApi and redirects on successful submit", async () => {
    mockLoginApi.mockResolvedValueOnce({ access_token: "jwt123" });

    render(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "user@test.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(mockLoginApi).toHaveBeenCalledWith("user@test.com", "password123");
      expect(mockLogin).toHaveBeenCalledWith("jwt123");
      expect(mockReplace).toHaveBeenCalledWith("/projects");
    });
  });

  it("shows error message on failed login", async () => {
    mockLoginApi.mockRejectedValueOnce(new Error("Invalid email or password"));

    render(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "bad@test.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument();
    });
  });

  it("shows resend verification button on EMAIL_NOT_VERIFIED error", async () => {
    // Import ApiError from the mock
    const { ApiError } = require("@/lib/authApi");
    mockLoginApi.mockRejectedValueOnce(
      new ApiError("Email not verified", 403, "EMAIL_NOT_VERIFIED")
    );

    render(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "unverified@test.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "pass");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText(/resend verification email/i)).toBeInTheDocument();
    });
  });

  it("shows forgot password link", () => {
    render(<LoginPage />);
    expect(screen.getByText(/forgot password/i)).toBeInTheDocument();
  });

  it("shows Back to Home link", () => {
    render(<LoginPage />);
    expect(screen.getByText(/back to home/i)).toBeInTheDocument();
  });
});
