/**
 * Behavioral / UI Tests for Home Page (Landing Page)
 *
 * Tests the marketing landing page renders correctly with login/signup links.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import Home from "@/app/page";

// Mock AuthProvider so the landing page renders its logged-out variant
jest.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    token: null,
    hydrated: true,
    isAuthenticated: false,
    login: jest.fn(),
    logout: jest.fn(),
  }),
}));

describe("Home (Landing Page)", () => {
  it("renders Blender Collab branding", () => {
    render(<Home />);
    // Appears in the navbar and footer — both should render
    expect(screen.getAllByText("Blender Collab").length).toBeGreaterThan(0);
  });

  it("renders hero headline", () => {
    render(<Home />);
    expect(screen.getByText(/Version control your/i)).toBeInTheDocument();
  });

  it("renders at least one Log In link pointing to /login", () => {
    render(<Home />);
    const loginLinks = screen.getAllByRole("link", { name: /log in/i });
    expect(loginLinks.length).toBeGreaterThan(0);
    expect(loginLinks[0]).toHaveAttribute("href", "/login");
  });

  it("renders at least one Sign Up link pointing to /signup", () => {
    render(<Home />);
    const signupLinks = screen.getAllByRole("link", { name: /sign up/i });
    expect(signupLinks.length).toBeGreaterThan(0);
    expect(signupLinks[0]).toHaveAttribute("href", "/signup");
  });
});
