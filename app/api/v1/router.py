from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, notes, chapters, students, assessments, reports,
    lesson_plans, question_papers, corrections, alerts,
    virtual_slate, analytics, translate, speech, content_search,
    subjects, assignments, notices, questions,
    classes, chapter_files, assignment_files, parent_notifications,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(notes.router)
api_router.include_router(chapters.router)
api_router.include_router(students.router)
api_router.include_router(assessments.router)
api_router.include_router(reports.router)
api_router.include_router(lesson_plans.router)
api_router.include_router(question_papers.router)
api_router.include_router(corrections.router)
api_router.include_router(alerts.router)
api_router.include_router(virtual_slate.router)
api_router.include_router(analytics.router)
api_router.include_router(translate.router)
api_router.include_router(speech.router)
api_router.include_router(content_search.router)
api_router.include_router(subjects.router)
api_router.include_router(assignments.router)
api_router.include_router(notices.router)
api_router.include_router(questions.router)
api_router.include_router(classes.router)
api_router.include_router(chapter_files.router)
api_router.include_router(assignment_files.router)
api_router.include_router(parent_notifications.router)
