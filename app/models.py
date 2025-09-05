from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Dict, Any, Optional

Base = declarative_base()

class RFPSubmission(Base):
    """Model for storing RFP submissions and their extracted data"""
    __tablename__ = "rfp_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_content = Column(Text, nullable=False)
    extracted_answers = Column(JSON, nullable=True)
    company_name = Column(String(255), nullable=True)
    submission_date = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_processed = Column(Boolean, default=False)
    s3_key = Column(String(500), nullable=True)  # S3 storage key
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "company_name": self.company_name,
            "submission_date": self.submission_date.isoformat() if self.submission_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_processed": self.is_processed,
            "extracted_answers": self.extracted_answers
        }

class RFPAnswer(Base):
    """Model for storing standardized RFP answers"""
    __tablename__ = "rfp_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    question_category = Column(String(100), nullable=False)  # e.g., "company_info", "technical_capabilities"
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    confidence_score = Column(Integer, nullable=True)  # 0-100 confidence in the answer
    source_rfp_id = Column(Integer, nullable=True)  # Reference to RFPSubmission
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "question_category": self.question_category,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "confidence_score": self.confidence_score,
            "source_rfp_id": self.source_rfp_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class RFPProcessingJob(Base):
    """Model for tracking RFP processing jobs"""
    __tablename__ = "rfp_processing_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
