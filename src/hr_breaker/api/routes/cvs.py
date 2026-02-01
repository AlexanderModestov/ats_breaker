"""CV management API routes."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.api.schemas import CVDeleteResponse, CVListResponse, CVResponse
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.supabase import SupabaseError

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "txt", "tex", "md", "html"}


def _extract_text(file_content: bytes, filename: str) -> str:
    """Extract text from uploaded file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        # Write to temp file for PDF parsing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(file_content)
            temp_path = Path(f.name)
        try:
            return extract_text_from_pdf(temp_path)
        finally:
            temp_path.unlink()
    else:
        # Text-based files
        return file_content.decode("utf-8")


@router.get("", response_model=CVListResponse)
async def list_cvs(
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> CVListResponse:
    """List all CVs for the current user."""
    try:
        cvs = supabase.list_cvs(user_id)
        return CVListResponse(
            cvs=[
                CVResponse(
                    id=cv["id"],
                    name=cv["name"],
                    original_filename=cv["original_filename"],
                    created_at=cv["created_at"],
                )
                for cv in cvs
            ]
        )
    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{cv_id}", response_model=CVResponse)
async def get_cv(
    cv_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> CVResponse:
    """Get a specific CV by ID."""
    cv = supabase.get_cv(cv_id, user_id)
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")

    return CVResponse(
        id=cv["id"],
        name=cv["name"],
        original_filename=cv["original_filename"],
        content_text=cv.get("content_text"),
        created_at=cv["created_at"],
    )


@router.post("", response_model=CVResponse)
async def upload_cv(
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
    file: UploadFile = File(...),
    name: str = Form(None),
) -> CVResponse:
    """Upload a new CV."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    file_content = await file.read()

    # Extract text
    try:
        content_text = _extract_text(file_content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text: {e}") from e

    # Use filename as name if not provided
    cv_name = name or file.filename.rsplit(".", 1)[0]

    try:
        # Upload to storage
        file_path = supabase.upload_cv_file(user_id, file_content, file.filename)

        # Create database record
        cv = supabase.create_cv(
            user_id=user_id,
            name=cv_name,
            file_path=file_path,
            original_filename=file.filename,
            content_text=content_text,
        )

        return CVResponse(
            id=cv["id"],
            name=cv["name"],
            original_filename=cv["original_filename"],
            content_text=cv.get("content_text"),
            created_at=cv["created_at"],
        )
    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{cv_id}", response_model=CVDeleteResponse)
async def delete_cv(
    cv_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> CVDeleteResponse:
    """Delete a CV."""
    try:
        success = supabase.delete_cv(cv_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="CV not found")
        return CVDeleteResponse(success=True, message="CV deleted successfully")
    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
