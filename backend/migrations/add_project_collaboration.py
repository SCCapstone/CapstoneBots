"""
Database Migration Script: Add Project Collaboration Tables

This script creates the project_members table and migrates existing projects
to include the owner as the first member.

Run this once to enable the collaboration feature:
    python backend/migrations/add_project_collaboration.py

Requirements:
- Database must be accessible via DATABASE_URL environment variable
- All existing projects will have their owners added as members with role='owner'
"""

import sys
import os
import asyncio

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database import DATABASE_URL, Base
from models import ProjectMember, Project, User

async def run_migration():
    """Execute the database migration"""
    
    print("=" * 70)
    print("Project Collaboration Migration")
    print("=" * 70)
    print()
    
    # Create async engine
    engine = create_async_engine(
        DATABASE_URL,
        echo=True,  # Show SQL statements
    )
    
    # Create async session factory
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with engine.begin() as conn:
            print("Step 1: Creating project_members table...")
            
            # Create the ProjectMember table
            await conn.run_sync(Base.metadata.create_all, tables=[ProjectMember.__table__])
            
            print("✓ project_members table created successfully!")
            print()
            
        # Now populate existing projects with owner memberships
        async with async_session() as session:
            print("Step 2: Migrating existing projects...")
            print("Adding project owners as members with role='owner'...")
            print()
            
            # Get all projects
            result = await session.execute(text("SELECT project_id, owner_id FROM projects"))
            projects = result.fetchall()
            
            if not projects:
                print("No existing projects found. Migration complete!")
                return
            
            added_count = 0
            for project in projects:
                project_id, owner_id = project
                
                # Check if membership already exists
                check_query = text("""
                    SELECT COUNT(*) FROM project_members 
                    WHERE project_id = :project_id AND user_id = :user_id
                """)
                existing = await session.execute(
                    check_query,
                    {"project_id": project_id, "user_id": owner_id}
                )
                count = existing.scalar()
                
                if count == 0:
                    # Add owner as member
                    insert_query = text("""
                        INSERT INTO project_members (member_id, project_id, user_id, role, added_by)
                        VALUES (gen_random_uuid(), :project_id, :user_id, 'owner', :added_by)
                    """)
                    await session.execute(
                        insert_query,
                        {
                            "project_id": project_id,
                            "user_id": owner_id,
                            "added_by": owner_id
                        }
                    )
                    added_count += 1
                    print(f"  ✓ Added owner membership for project {project_id}")
            
            await session.commit()
            
            print()
            print(f"✓ Migration completed successfully!")
            print(f"  - Total projects processed: {len(projects)}")
            print(f"  - Owner memberships added: {added_count}")
            print()
            print("=" * 70)
            print("The collaboration feature is now ready to use!")
            print("=" * 70)
            
    except Exception as e:
        print()
        print("❌ Migration failed!")
        print(f"Error: {str(e)}")
        print()
        raise
    
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print()
    print("Starting database migration...")
    print()
    
    try:
        asyncio.run(run_migration())
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed with error: {str(e)}")
        sys.exit(1)
