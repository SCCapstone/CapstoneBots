"""
Local collaboration test:
1) Register two random users
2) Login as user A
3) Create a project
4) Add user B by email
5) Confirm project has 2 members

Run:
  python test_add_member_flow.py
"""

import os
import json
import random
import string
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def rand_suffix(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def register_user(username: str, email: str, password: str) -> None:
    res = requests.post(
        f"{BASE_URL}/api/auth/register",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": username, "email": email, "password": password}),
        timeout=10,
    )
    if res.status_code not in (200, 201):
        raise RuntimeError(f"Register failed ({res.status_code}): {res.text}")


def login_user(email: str, password: str) -> str:
    res = requests.post(
        f"{BASE_URL}/api/auth/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"email": email, "password": password}),
        timeout=10,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Login failed ({res.status_code}): {res.text}")
    return res.json()["access_token"]


def create_project(token: str, name: str) -> dict:
    res = requests.post(
        f"{BASE_URL}/api/projects",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        data=json.dumps({"name": name, "description": "Collab test", "active": True}),
        timeout=10,
    )
    if res.status_code not in (200, 201):
        raise RuntimeError(f"Create project failed ({res.status_code}): {res.text}")
    return res.json()


def add_member(token: str, project_id: str, email: str) -> dict:
    res = requests.post(
        f"{BASE_URL}/api/projects/{project_id}/members",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        data=json.dumps({"email": email}),
        timeout=10,
    )
    if res.status_code not in (200, 201):
        raise RuntimeError(f"Add member failed ({res.status_code}): {res.text}")
    return res.json()


def get_members(token: str, project_id: str) -> list:
    res = requests.get(
        f"{BASE_URL}/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if res.status_code != 200:
        raise RuntimeError(f"List members failed ({res.status_code}): {res.text}")
    return res.json()


def main() -> None:
    suffix = rand_suffix()
    user_a = {
        "username": f"usera_{suffix}",
        "email": f"usera_{suffix}@example.com",
        "password": "password123",
    }
    user_b = {
        "username": f"userb_{suffix}",
        "email": f"userb_{suffix}@example.com",
        "password": "password123",
    }

    print("Registering users...")
    register_user(**user_a)
    register_user(**user_b)

    print("Logging in as user A...")
    token_a = login_user(user_a["email"], user_a["password"])

    print("Creating project...")
    project = create_project(token_a, f"Collab Project {suffix}")
    project_id = project["project_id"]

    print("Adding user B as member...")
    add_member(token_a, project_id, user_b["email"])

    print("Fetching members...")
    members = get_members(token_a, project_id)

    print("Members:")
    for member in members:
        print(f"- {member['email']} ({member['role']})")

    if len(members) != 2:
        raise RuntimeError(f"Expected 2 members, found {len(members)}")

    print("\n✅ Collaboration add-member flow works (2 members confirmed).")


if __name__ == "__main__":
    main()
