from .db import Base, engine, SessionLocal
from .services import seed
Base.metadata.create_all(bind=engine)
db=SessionLocal()
try:
    seed(db)
    print("Seed complete")
finally:
    db.close()
