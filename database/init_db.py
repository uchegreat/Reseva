from database.db import Base, engine
from database import models


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Reseva database tables created successfully.")