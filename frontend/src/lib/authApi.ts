const API_BASE = process.env.BACKEND_URL || "http://localhost:8000";

export type SignupPayload = {
  email: string;
  password: string;
  name?: string;
  username?: string;
};

export async function loginApi(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(`Login failed: ${res.status}`);
  }
  return res.json();
}
 
export async function signupApi(payload: SignupPayload) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Signup failed: ${res.status}`);
  }
  return res.json();
}
