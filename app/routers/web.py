"""
Web pages routes: legal and safety pages.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["web"])


@router.get("/terms")
def get_terms():
    """Get Terms of Service page."""
    return FileResponse("web/terms.html", media_type="text/html")


@router.get("/privacy")
def get_privacy():
    """Get Privacy Policy page."""
    return FileResponse("web/privacy.html", media_type="text/html")


@router.get("/child-safety")
def get_child_safety():
    """Get Child Safety Policy page."""
    return FileResponse("web/child-safety.html", media_type="text/html")
