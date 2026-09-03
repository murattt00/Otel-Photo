"""
Operator (foto yukleyen eleman) paneli sayfasi.

Simdilik urun/albuw yonetimini barindirir. Ilerde foto yukleme arayuzu de buraya eklenebilir.
"""
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi import APIRouter

router = APIRouter(prefix="/operator", tags=["operator"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("")
def operator_page():
    """Operator panelini dondurur."""
    return FileResponse(STATIC_DIR / "operator.html")
