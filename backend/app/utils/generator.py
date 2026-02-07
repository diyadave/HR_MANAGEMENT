import secrets
import string
from datetime import datetime

def generate_employee_id(count: int) -> str:
    year = datetime.now().year
    return f"EMP{year}{count+1:04d}"

def generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits + "@$#"
    return "".join(secrets.choice(chars) for _ in range(length))
