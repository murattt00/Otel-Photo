"""
Veritabani baglantisi ve oturum (session) yonetimi.

- engine     : PostgreSQL'e acilan baglanti havuzu
- SessionLocal: her istek/islem icin yeni bir DB oturumu uretir
- Base        : tum ORM modellerinin miras alacagi taban sinif
- get_db      : FastAPI dependency'si; her istekte bir oturum acar, sonunda kapatir
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# pool_pre_ping: kopmus baglantilari otomatik yeniler (uzun sure bosta kalma sonrasi hatalari onler)
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Tum modeller bu sinifi miras alir. Alembic bu Base.metadata'yi kullanir."""
    pass


def get_db():
    """FastAPI dependency: her istek icin bir DB oturumu acar, istek bitince kapatir."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
