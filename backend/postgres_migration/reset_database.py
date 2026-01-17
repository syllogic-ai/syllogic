"""
Script to reset the database by dropping all tables and recreating them.
WARNING: This will delete all data!
"""
from sqlalchemy import inspect, text
from app.database import engine, Base
from app.models import (
    User, Account, Category, Transaction,
    CategorizationRule, BankConnection
)

def reset_database():
    """Drop all tables and recreate them with the new schema."""
    print("⚠️  WARNING: This will delete all existing data!")
    
    # Close all existing connections
    print("Closing existing connections...")
    engine.dispose()
    
    # Use a fresh connection
    with engine.connect() as conn:
        # Terminate any active connections to the database (except ours)
        print("Terminating active database connections...")
        try:
            conn.execute(text("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = current_database()
                AND pid <> pg_backend_pid();
            """))
            conn.commit()
            print("✓ Active connections terminated")
        except Exception as e:
            print(f"⚠ Could not terminate connections: {e}")
        
        print("\nDropping all existing tables...")
        
        # Get all table names
        result = conn.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        tables = [row[0] for row in result]
        
        if tables:
            print(f"Found {len(tables)} tables to drop")
            
            # Drop tables individually with explicit commits
            for table_name in tables:
                try:
                    print(f"  Dropping {table_name}...", end=" ", flush=True)
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))
                    conn.commit()
                    print("✓")
                except Exception as e:
                    print(f"✗ Error: {e}")
                    conn.rollback()
            
            print("\n✓ All tables dropped")
        else:
            print("No tables found - database is already empty")
    
    # Dispose connection before creating tables
    engine.dispose()
    
    print("\nCreating new tables with updated schema...")
    # Create all tables with new schema
    Base.metadata.create_all(bind=engine)
    print("✓ All tables created successfully!")
    
    print("\nCreated tables:")
    inspector = inspect(engine)
    for table_name in sorted(inspector.get_table_names()):
        print(f"  - {table_name}")
    
    print("\n✅ Database reset complete! You can now run seed_data.py")

if __name__ == "__main__":
    reset_database()
