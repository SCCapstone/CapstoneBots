/**
 * Behavioral / UI Tests for CommitItem Component
 *
 * Tests commit rendering: message, short hash, and timestamp formatting.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import CommitItem from "@/components/CommitItem";
import type { Commit } from "@/lib/projectsApi";

function makeCommit(overrides: Partial<Commit> = {}): Commit {
  return {
    commit_id: "c-1",
    project_id: "p-1",
    branch_id: "b-1",
    parent_commit_id: null,
    author_id: "a-1",
    commit_hash: "abc1234567890",
    commit_message: "Initial commit",
    committed_at: "2025-06-15T12:00:00Z",
    ...overrides,
  };
}

describe("CommitItem", () => {
  it("renders commit message", () => {
    render(<CommitItem commit={makeCommit()} />);
    expect(screen.getByText("Initial commit")).toBeInTheDocument();
  });

  it("renders short hash (first 7 chars)", () => {
    render(<CommitItem commit={makeCommit({ commit_hash: "abcdef1234567890" })} />);
    expect(screen.getByText("abcdef1")).toBeInTheDocument();
  });

  it("renders (no message) when commit_message is empty", () => {
    render(<CommitItem commit={makeCommit({ commit_message: "" })} />);
    expect(screen.getByText("(no message)")).toBeInTheDocument();
  });

  it("renders formatted date", () => {
    render(<CommitItem commit={makeCommit({ committed_at: "2025-12-25T10:30:00Z" })} />);
    // The exact format depends on the locale, just check it contains something date-like
    const container = screen.getByText(/Initial commit/).closest("div")!.parentElement!;
    expect(container.textContent).toContain("2025");
  });

  it("renders raw string for invalid date", () => {
    render(<CommitItem commit={makeCommit({ committed_at: "not-a-date" })} />);
    const container = screen.getByText(/Initial commit/).closest("div")!.parentElement!;
    expect(container.textContent).toContain("not-a-date");
  });
});
