"""
List all users, projects, and project memberships (local DB).

Run:
  python list_users_projects.py

Optional:
  BASE_URL env not needed (uses DB directly).
"""

import asyncio
from sqlalchemy import select

from database import AsyncSessionLocal
from models import User, Project, ProjectMember


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print("=" * 70)
        print("Users")
        print("=" * 70)
        users_result = await session.execute(select(User).order_by(User.created_at.asc()))
        users = users_result.scalars().all()
        if not users:
            print("No users found.")
        else:
            for user in users:
                print(f"- {user.user_id} | {user.username} | {user.email} | created: {user.created_at}")

        print("\n" + "=" * 70)
        print("Projects")
        print("=" * 70)
        projects_result = await session.execute(select(Project).order_by(Project.created_at.asc()))
        projects = projects_result.scalars().all()
        if not projects:
            print("No projects found.")
        else:
            for project in projects:
                print(
                    f"- {project.project_id} | {project.name} | owner: {project.owner_id} | created: {project.created_at}"
                )

        print("\n" + "=" * 70)
        print("Project Members")
        print("=" * 70)
        members_result = await session.execute(
            select(ProjectMember, User, Project)
            .join(User, ProjectMember.user_id == User.user_id)
            .join(Project, ProjectMember.project_id == Project.project_id)
            .order_by(ProjectMember.added_at.asc())
        )
        members = members_result.all()
        if not members:
            print("No project members found.")
        else:
            for member, user, project in members:
                print(
                    "- "
                    f"project: {project.name} ({project.project_id}) | "
                    f"user: {user.username} ({user.email}) | "
                    f"role: {member.role} | added: {member.added_at}"
                )


if __name__ == "__main__":
    asyncio.run(main())
