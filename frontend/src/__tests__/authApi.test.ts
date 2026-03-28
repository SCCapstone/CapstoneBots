/**
 * Unit Tests for authApi.ts
 *
 * Tests the API client functions with mocked fetch.
 * Covers normal responses, error responses, and edge cases.
 */

import { ApiError, loginApi, signupApi, deleteAccount } from "@/lib/authApi";

// ============== Mock fetch globally ==============

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

// ============== loginApi ==============

describe("loginApi", () => {
  it("returns token on successful login", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: "jwt-token-123", token_type: "bearer" }),
    });

    const result = await loginApi("user@example.com", "password");
    expect(result.access_token).toBe("jwt-token-123");
    expect(result.token_type).toBe("bearer");
  });

  it("sends correct payload", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: "tok" }),
    });

    await loginApi("test@test.com", "pass123");

    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.email).toBe("test@test.com");
    expect(body.password).toBe("pass123");
    expect(options.method).toBe("POST");
  });

  it("throws ApiError with status on invalid credentials", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Invalid email or password" }),
    });

    try {
      await loginApi("bad@email.com", "wrong");
      fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(401);
    }
  });

  it("throws ApiError with EMAIL_NOT_VERIFIED code on 403", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({
        detail: { message: "Email not verified", code: "EMAIL_NOT_VERIFIED" },
      }),
    });

    try {
      await loginApi("user@example.com", "pass");
      fail("should have thrown");
    } catch (e) {
      const err = e as ApiError;
      expect(err.status).toBe(403);
      expect(err.code).toBe("EMAIL_NOT_VERIFIED");
    }
  });

  it("handles non-JSON error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => { throw new Error("no json"); },
    });

    await expect(loginApi("a@b.com", "p")).rejects.toThrow();
  });
});

// ============== signupApi ==============

describe("signupApi", () => {
  it("returns user data on success", async () => {
    const userData = { user_id: "uuid-1", email: "new@user.com", username: "newuser" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => userData,
    });

    const result = await signupApi({ username: "newuser", email: "new@user.com", password: "pass1234" });
    expect(result.user_id).toBe("uuid-1");
  });

  it("sends correct payload", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    await signupApi({ username: "alice", email: "alice@test.com", password: "secure" });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.username).toBe("alice");
    expect(body.email).toBe("alice@test.com");
    expect(body.password).toBe("secure");
  });

  it("throws Error on duplicate email", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Email already registered" }),
    });

    await expect(
      signupApi({ username: "a", email: "dup@test.com", password: "p" })
    ).rejects.toThrow("Email already registered");
  });

  it("throws generic error when no JSON body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => { throw new Error("fail"); },
    });

    await expect(
      signupApi({ username: "a", email: "b@c.com", password: "p" })
    ).rejects.toThrow("Signup failed");
  });

  it("handles validation error array", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          { msg: "password too short" },
          { msg: "invalid email" },
        ],
      }),
    });

    await expect(
      signupApi({ username: "x", email: "x", password: "x" })
    ).rejects.toThrow(/password too short/);
  });
});

// ============== deleteAccount ==============

describe("deleteAccount", () => {
  it("resolves on 204", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
    });

    await expect(deleteAccount("token", "password")).resolves.toBeUndefined();
  });

  it("throws on wrong password (401)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Incorrect password" }),
    });

    await expect(deleteAccount("token", "wrong")).rejects.toThrow("Incorrect password");
  });

  it("sends auth header and password", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });

    await deleteAccount("my-jwt", "my-pass");

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer my-jwt");
    expect(JSON.parse(options.body).password).toBe("my-pass");
    expect(options.method).toBe("DELETE");
  });
});
