import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PROJECT_DESCRIPTION_MAX_LENGTH, PROJECT_NAME_MAX_LENGTH } from "@/lib/validation";

const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: mockReplace,
  }),
}));

jest.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    token: "test-token",
    hydrated: true,
    isAuthenticated: true,
    login: jest.fn(),
    logout: jest.fn(),
  }),
}));

const mockFetchProjects = jest.fn();
const mockCreateProject = jest.fn();
const mockFetchPendingInvitations = jest.fn();

jest.mock("@/lib/projectsApi", () => ({
  fetchProjects: (...args: unknown[]) => mockFetchProjects(...args),
  createProject: (...args: unknown[]) => mockCreateProject(...args),
  fetchPendingInvitations: (...args: unknown[]) => mockFetchPendingInvitations(...args),
}));

import ProjectsPage from "@/app/projects/page";

beforeEach(() => {
  jest.clearAllMocks();
  mockFetchProjects.mockResolvedValue([]);
  mockFetchPendingInvitations.mockResolvedValue([]);
  mockCreateProject.mockResolvedValue({
    project_id: "p-1",
    name: "Demo Project",
    description: "Desc",
    updated_at: "2025-01-01T12:00:00Z",
  });
});

describe("ProjectsPage", () => {
  it("renders project updated_at using the shared local-time formatter", async () => {
    mockFetchProjects.mockResolvedValue([
      {
        project_id: "p-1",
        name: "Demo Project",
        description: "Desc",
        updated_at: "2025-01-01T12:00:00",
      },
    ]);

    render(<ProjectsPage />);

    const expected = new Date("2025-01-01T12:00:00Z").toLocaleString();

    await waitFor(() => {
      expect(screen.getByText(new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeInTheDocument();
    });
  });

  it("applies max length attributes in the create project form", async () => {
    render(<ProjectsPage />);

    await userEvent.click(screen.getByRole("button", { name: /\+ new project/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /create new project/i })).toBeInTheDocument();
    });

    expect(screen.getByPlaceholderText("Blender Environment v1")).toHaveAttribute(
      "maxLength",
      String(PROJECT_NAME_MAX_LENGTH)
    );

    expect(screen.getByPlaceholderText("Short description of this Blender project...")).toHaveAttribute(
      "maxLength",
      String(PROJECT_DESCRIPTION_MAX_LENGTH)
    );
  });
});
