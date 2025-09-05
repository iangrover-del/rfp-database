from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import tempfile
import shutil
from pathlib import Path

from app.database import get_db, create_tables
from app.services import RFPService
from app.models import RFPSubmission, RFPProcessingJob

# Create FastAPI app
app = FastAPI(
    title="RFP Database API",
    description="AI-powered RFP database for automatic answer extraction and matching",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "RFP Database API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/upload",
            "process": "/process",
            "submissions": "/submissions",
            "search": "/search",
            "statistics": "/statistics"
        }
    }

@app.post("/upload")
async def upload_rfp_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload and ingest an RFP document into the database"""
    
    # Validate file type
    allowed_extensions = ['.pdf', '.docx', '.xlsx', '.xls', '.txt']
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name
    
    try:
        # Process the document
        rfp_service = RFPService(db)
        result = rfp_service.ingest_rfp_document(temp_file_path, file.filename)
        
        return JSONResponse(content=result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@app.post("/process")
async def process_new_rfp(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Process a new RFP and get suggested answers from existing submissions"""
    
    # Validate file type
    allowed_extensions = ['.pdf', '.docx', '.xlsx', '.xls', '.txt']
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name
    
    try:
        # Process the new RFP
        rfp_service = RFPService(db)
        result = rfp_service.process_new_rfp(temp_file_path, file.filename)
        
        return JSONResponse(content=result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@app.get("/submissions")
async def get_rfp_submissions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get all RFP submissions with pagination"""
    
    rfp_service = RFPService(db)
    submissions = rfp_service.get_all_rfp_submissions(limit=limit, offset=offset)
    
    return {
        "submissions": submissions,
        "limit": limit,
        "offset": offset,
        "total": len(submissions)
    }

@app.get("/submissions/{rfp_id}")
async def get_rfp_submission(
    rfp_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific RFP submission by ID"""
    
    rfp_service = RFPService(db)
    submission = rfp_service.get_rfp_submission(rfp_id)
    
    if not submission:
        raise HTTPException(status_code=404, detail="RFP submission not found")
    
    return submission

@app.get("/search")
async def search_rfp_submissions(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Search RFP submissions by content, company name, or filename"""
    
    rfp_service = RFPService(db)
    results = rfp_service.search_rfp_submissions(q, limit=limit)
    
    return {
        "query": q,
        "results": results,
        "total": len(results)
    }

@app.get("/statistics")
async def get_statistics(db: Session = Depends(get_db)):
    """Get database statistics and recent activity"""
    
    rfp_service = RFPService(db)
    stats = rfp_service.get_statistics()
    
    return stats

@app.get("/jobs")
async def get_processing_jobs(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get recent processing jobs"""
    
    rfp_service = RFPService(db)
    jobs = rfp_service.get_processing_jobs(limit=limit)
    
    return {
        "jobs": jobs,
        "total": len(jobs)
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "RFP Database API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
