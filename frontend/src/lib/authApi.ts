const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type SignupPayload = {
  username: string;
  email: string;
  password: string;
};

export type MeResponse = {
  user_id: string;
  username: string;
  email: string;
  created_at: string;
};

export async function fetchCurrentUser(token: string): Promise<MeResponse> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    console.log(res.json());
    throw new Error("Failed to fetch current user");
  }

  return res.json();
}


/**
 * Structured error thrown by API helpers.
 * Carries the HTTP status and an optional machine-readable code
 * so callers can branch without parsing human-readable text.
 */
export class ApiError extends Error {
  status: number;
  code: string | undefined;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function loginApi(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    let message = "Invalid email or password.";
    let code: string | undefined;
    try {
      const data = await res.json();
      if (data?.detail) {
        if (typeof data.detail === "string") {
          message = data.detail;
        } else if (typeof data.detail === "object") {
          message = data.detail.message ?? message;
          code = data.detail.code;
        }
      }
    } catch {
      /* no JSON */
    }
    throw new ApiError(message, res.status, code);
  }
  return res.json();
}

export async function signupApi(payload: SignupPayload) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let message = "Signup failed";

    try {
      const data = await res.json();

      if (data?.detail) {
        // Backend may return a string or a list
        if (typeof data.detail === "string") {
          message = data.detail;
        } else if (Array.isArray(data.detail)) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          message = data.detail.map((d: any) => d.msg || d.detail).join(", ");
        }
      }
    } catch {
      /* backend returned no JSON */
    }

    throw new Error(message);
  }

  return res.json();
}

export async function deleteAccount(token: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/account`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ password }),
  });

  if (res.status === 204) {
    return;
  }

  if (!res.ok) {
    let message = "Account deletion failed";
    try {
      const data = await res.json();
      if (data?.detail) {
        message = typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            ? data.detail.map((d: any) => d.msg || d.detail).join(", ")
            : message;
      }
    } catch {
      /* no JSON body */
    }
    throw new Error(message);
  }
}
export async function forgotPasswordApi(email: string) {
  const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const data = await res.json();
      if (data?.detail && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      /* no JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

export async function resetPasswordApi(token: string, newPassword: string) {
  const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) {
    let message = "Password reset failed";
    try {
      const data = await res.json();
      if (data?.detail && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      /* no JSON */
    }
    throw new Error(message);
  }
  return res.json();
}


export async function verifyEmailApi(token: string) {
  const res = await fetch(`${API_BASE}/api/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    let message = "Email verification failed";
    try {
      const data = await res.json();
      if (data?.detail && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      /* no JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

export async function resendVerificationApi(email: string) {
  const res = await fetch(`${API_BASE}/api/auth/resend-verification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    let message = "Failed to resend verification email";
    try {
      const data = await res.json();
      if (data?.detail && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      /* no JSON */
    }
    throw new Error(message);
  }
  return res.json();
}
