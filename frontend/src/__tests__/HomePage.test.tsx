/**
 * Behavioral / UI Tests for Home Page (Landing Page)
 *
 * Tests the landing page renders correctly with login/signup buttons.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import Home from "@/app/page";

describe("Home (Landing Page)", () => {
  it("renders Blender Collab title", () => {
    render(<Home />);
    expect(screen.getByText("Blender Collab")).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<Home />);
    expect(
      screen.getByText(/lightweight Blender collaboration/i)
    ).toBeInTheDocument();
  });

  it("renders Log In link", () => {
    render(<Home />);
    const loginLink = screen.getByRole("link", { name: /log in/i });
    expect(loginLink).toBeInTheDocument();
    expect(loginLink).toHaveAttribute("href", "/login");
  });

  it("renders Sign Up link", () => {
    render(<Home />);
    const signupLink = screen.getByRole("link", { name: /sign up/i });
    expect(signupLink).toBeInTheDocument();
    expect(signupLink).toHaveAttribute("href", "/signup");
  });
});
