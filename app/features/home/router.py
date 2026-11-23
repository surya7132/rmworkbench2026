"""The front door: "/" goes to the work queue."""
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/")
def home():
    return RedirectResponse("/work", status_code=303)
