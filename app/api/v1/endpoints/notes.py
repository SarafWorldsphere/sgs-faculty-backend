from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_teacher, get_active_class_id
from app.models.teacher import TeacherMaster
from app.schemas.note import NoteCreate, NoteUpdate, NoteOut, NoteListResponse
from app.services import note_service

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=NoteListResponse)
def list_notes(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
    class_id=Depends(get_active_class_id),
):
    """The teacher's notes for the class they are currently working on."""
    notes = note_service.get_notes(db, teacher.teacher_id, class_id)
    return NoteListResponse(notes=notes, total=len(notes))


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
    class_id=Depends(get_active_class_id),
):
    """Create a note, stamped with the class it was written for."""
    return note_service.create_note(db, teacher.teacher_id, payload, class_id)


@router.get("/deleted", response_model=NoteListResponse)
def list_deleted_notes(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Soft-deleted notes, restorable until the year-end purge.
    Declared before /{note_id} so "deleted" is not parsed as an id."""
    notes = note_service.get_deleted_notes(db, teacher.teacher_id)
    return NoteListResponse(notes=notes, total=len(notes))


@router.get("/{note_id}", response_model=NoteOut)
def get_note(
    note_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    note = note_service.get_note(db, teacher.teacher_id, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.put("/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    note = note_service.update_note(db, teacher.teacher_id, note_id, payload)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Soft delete — the note disappears from lists but can be restored."""
    deleted = note_service.delete_note(db, teacher.teacher_id, note_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


@router.post("/{note_id}/restore", response_model=NoteOut)
def restore_note(
    note_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    note = note_service.restore_note(db, teacher.teacher_id, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No deleted note with that id")
    return note
