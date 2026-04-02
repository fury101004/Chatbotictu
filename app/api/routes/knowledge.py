from __future__ import annotations

from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status


router = APIRouter(tags=["knowledge"])


def _knowledge_service():
    try:
        from app.services import knowledge_base_service
    except (ModuleNotFoundError, ImportError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Knowledge service chưa sẵn sàng vì thiếu dependency: "
                f"{getattr(exc, 'name', None) or exc.__class__.__name__}."
            ),
        ) from exc

    return knowledge_base_service


@router.get("/api/vector/status")
def api_vector_status():
    return _knowledge_service().get_vector_status()


@router.get("/api/knowledge/jobs")
def api_knowledge_jobs(limit: int = 10):
    return {"jobs": _knowledge_service().list_knowledge_jobs(limit=limit)}


@router.get("/api/knowledge/jobs/{job_id}")
def api_knowledge_job(job_id: str):
    job = _knowledge_service().get_knowledge_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy knowledge job.")
    return job


@router.post("/api/vector/rebuild", status_code=status.HTTP_202_ACCEPTED)
def api_vector_rebuild():
    service = _knowledge_service()
    try:
        job = service.start_rebuild_job()
        return {
            "message": "Đã tiếp nhận yêu cầu rebuild vector store.",
            "job": job,
            "status": service.get_vector_status(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Không thể rebuild vector store lúc này.",
        ) from exc


@router.post("/api/upload", status_code=status.HTTP_202_ACCEPTED)
def api_upload(
    route: str = Form("policy"),
    files: List[UploadFile] = File(...),
):
    service = _knowledge_service()
    try:
        job = service.start_upload_job(files, route)
        return {
            "message": "Đã tiếp nhận file upload và đưa vào hàng đợi rebuild.",
            "job": job,
            "status": service.get_vector_status(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Upload thất bại hoặc không thể cập nhật vector store.",
        ) from exc
