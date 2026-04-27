/**
 * Behavioral / UI Tests for Signup Page
 *
 * Simulates user interactions: form validation, password mismatch, and successful signup.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH } from "@/lib/validation";

// ============== Mocks ==============

const mockReplace = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: mockReplace,
  }),
}));

jest.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    token: null,
    hydrated: true,
    isAuthenticated: false,
    login: jest.fn(),
    logout: jest.fn(),
  }),
}));

const mockSignupApi = jest.fn();
jest.mock("@/lib/authApi", () => ({
  signupApi: (...args: unknown[]) => mockSignupApi(...args),
  SignupPayload: {},
}));

import SignupPage from "@/app/signup/page";

beforeEach(() => {
  jest.clearAllMocks();
});

describe("SignupPage", () => {
  it("renders all form fields", () => {
    render(<SignupPage />);

    expect(screen.getByPlaceholderText("Your username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    // Two password fields
    const passwordFields = screen.getAllByPlaceholderText("••••••••");
    expect(passwordFields).toHaveLength(2);
  });

  it("renders Sign Up button", () => {
    render(<SignupPage />);
    expect(screen.getByRole("button", { name: /sign up/i })).toBeInTheDocument();
  });

  it("shows Blender Collab branding", () => {
    render(<SignupPage />);
    expect(screen.getByText("Blender Collab")).toBeInTheDocument();
  });

  it("shows password length requirement", () => {
    render(<SignupPage />);
    expect(screen.getByText(/must be at least 8 characters/i)).toBeInTheDocument();
  });

  it("shows error when passwords don't match", async () => {
    render(<SignupPage />);

    await userEvent.type(screen.getByPlaceholderText("Your username"), "testuser");
    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");

    const [password, confirm] = screen.getAllByPlaceholderText("••••••••");
    await userEvent.type(password, "password123");
    await userEvent.type(confirm, "differentpassword");

    await userEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
    expect(mockSignupApi).not.toHaveBeenCalled();
  });

  it("calls signupApi and shows success message", async () => {
    mockSignupApi.mockResolvedValueOnce({ user_id: "uuid-1", email: "new@test.com" });

    render(<SignupPage />);

    await userEvent.type(screen.getByPlaceholderText("Your username"), "newuser");
    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "new@test.com");

    const [password, confirm] = screen.getAllByPlaceholderText("••••••••");
    await userEvent.type(password, "securepass");
    await userEvent.type(confirm, "securepass");

    await userEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(mockSignupApi).toHaveBeenCalledWith({
        username: "newuser",
        email: "new@test.com",
        password: "securepass",
      });
      expect(screen.getByText(/account created/i)).toBeInTheDocument();
      expect(screen.getByText(/go to login/i)).toBeInTheDocument();
    });
  });

  it("shows API error message on signup failure", async () => {
    mockSignupApi.mockRejectedValueOnce(new Error("Email already registered"));

    render(<SignupPage />);

    await userEvent.type(screen.getByPlaceholderText("Your username"), "user");
    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "dup@test.com");

    const [password, confirm] = screen.getAllByPlaceholderText("••••••••");
    await userEvent.type(password, "password123");
    await userEvent.type(confirm, "password123");

    await userEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(screen.getByText(/email already registered/i)).toBeInTheDocument();
    });
  });

  it("has a link to log in page", () => {
    render(<SignupPage />);
    expect(screen.getByText(/log in/i)).toBeInTheDocument();
  });

  it("has a back to home link", () => {
    render(<SignupPage />);
    expect(screen.getByText(/back to home/i)).toBeInTheDocument();
  });

  it("applies max length attributes to username and password inputs", () => {
    render(<SignupPage />);

    expect(screen.getByPlaceholderText("Your username")).toHaveAttribute("maxLength", String(USERNAME_MAX_LENGTH));

    const [password, confirm] = screen.getAllByPlaceholderText("â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢");
    expect(password).toHaveAttribute("maxLength", String(PASSWORD_MAX_LENGTH));
    expect(confirm).toHaveAttribute("maxLength", String(PASSWORD_MAX_LENGTH));
  });
});
