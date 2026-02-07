from app.database.session import SessionLocal
from app.models.user import User
from app.core.security import hash_password

def create_admin():
    db = SessionLocal()

    existing_admin = db.query(User).filter(User.role == "admin").first()
    if existing_admin:
        print("Admin already exists")
        return

    admin = User(
        name="System Admin",
        email="admin@company.com",
        password_hash=hash_password("Admin@123"),
        role="admin",
        force_password_change=False
    )

    db.add(admin)
    db.commit()
    db.close()

    print("Admin created successfully")

if __name__ == "__main__":
    create_admin()
