from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Project
from app.schemas.project import (
    GuestImportRequest,
    GuestSummary,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectResponse,
)
from app.services.simulation.service import create_project, get_project_or_404, import_guests

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project_endpoint(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = create_project(db, payload)
    return serialize_project(project)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project_endpoint(project_id: str, db: Session = Depends(get_db)) -> ProjectDetailResponse:
    project = get_project_or_404(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return serialize_project_detail(project)


@router.post("/{project_id}/guests/import", response_model=ProjectDetailResponse)
def import_guests_endpoint(
    project_id: str,
    payload: GuestImportRequest,
    db: Session = Depends(get_db),
) -> ProjectDetailResponse:
    project = get_project_or_404(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    import_guests(db, project, payload)
    db.refresh(project)
    return serialize_project_detail(project)


def serialize_project(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        guest_count=len(project.guests),
        created_at=project.created_at,
    )


def serialize_project_detail(project: Project) -> ProjectDetailResponse:
    return ProjectDetailResponse(
        **serialize_project(project).model_dump(),
        guests=[
            GuestSummary(
                id=guest.id,
                name=guest.name,
                role=guest.role,
                city=guest.city,
                occupation=guest.occupation,
                attachment_style=guest.attachment_style,
            )
            for guest in project.guests
        ],
    )

