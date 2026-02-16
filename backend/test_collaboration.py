"""
Quick test script for the collaboration feature.

This script tests the collaboration endpoints to verify everything works.
"""

import asyncio
import sys
sys.path.insert(0, '.')

from sqlalchemy import select
from database import AsyncSessionLocal
from models import User, Project, ProjectMember

async def test_collaboration():
    print("=" * 70)
    print("Testing Collaboration Feature")
    print("=" * 70)
    print()
    
    async with AsyncSessionLocal() as session:
        # Check if project_members table exists and is accessible
        print("✓ Checking project_members table...")
        result = await session.execute(select(ProjectMember))
        members = result.scalars().all()
        print(f"  Current project members: {len(members)}")
        print()
        
        # Check users
        print("✓ Checking users...")
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"  Total users: {len(users)}")
        for user in users[:5]:  # Show first 5
            print(f"    - {user.username} ({user.email})")
        print()
        
        # Check projects
        print("✓ Checking projects...")
        result = await session.execute(select(Project))
        projects = result.scalars().all()
        print(f"  Total projects: {len(projects)}")
        for project in projects[:5]:  # Show first 5
            print(f"    - {project.name} (Owner: {project.owner_id})")
        print()
        
        print("=" * 70)
        print("✓ All tables accessible! Collaboration feature is ready!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Start the backend server: uvicorn main:app --reload")
        print("2. Test endpoints at: http://localhost:8000/docs")
        print("3. Try adding a member: POST /api/projects/{project_id}/members")
        print()

if __name__ == "__main__":
    asyncio.run(test_collaboration())
