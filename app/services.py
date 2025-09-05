import os
import tempfile
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import RFPSubmission, RFPAnswer, RFPProcessingJob
from app.document_processor import RFPAnswerExtractor, RFPAnswerMatcher
from app.aws_storage import DocumentStorage
from datetime import datetime

class RFPService:
    """Main service class for RFP operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.s3_bucket = os.getenv("S3_BUCKET_NAME", "rfp-database-bucket")
        
        # Initialize components
        self.answer_extractor = RFPAnswerExtractor(self.openai_api_key)
        self.answer_matcher = RFPAnswerMatcher(self.openai_api_key)
        self.document_storage = DocumentStorage(self.s3_bucket)
    
    def ingest_rfp_document(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Ingest a new RFP document into the database"""
        
        try:
            # Create processing job record
            job = RFPProcessingJob(
                filename=filename,
                status="processing",
                progress=10
            )
            self.db.add(job)
            self.db.commit()
            
            # Store document in S3
            storage_info = self.document_storage.store_rfp_document(file_path, filename)
            
            # Update job progress
            job.progress = 30
            self.db.commit()
            
            # Extract answers using AI
            extracted_data = self.answer_extractor.extract_answers_from_rfp(file_path, filename)
            
            # Update job progress
            job.progress = 70
            self.db.commit()
            
            # Save to database
            rfp_submission = RFPSubmission(
                filename=filename,
                original_content=extracted_data["original_content"],
                extracted_answers=extracted_data["extracted_answers"],
                company_name=extracted_data["company_name"],
                is_processed=True,
                s3_key=storage_info["s3_key"]
            )
            
            self.db.add(rfp_submission)
            self.db.commit()
            
            # Update job as completed
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now()
            self.db.commit()
            
            return {
                "success": True,
                "rfp_id": rfp_submission.id,
                "job_id": job.id,
                "message": "RFP document successfully ingested and processed"
            }
            
        except Exception as e:
            # Update job as failed
            if 'job' in locals():
                job.status = "failed"
                job.error_message = str(e)
                self.db.commit()
            
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to ingest RFP document"
            }
    
    def get_all_rfp_submissions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all RFP submissions with pagination"""
        
        submissions = self.db.query(RFPSubmission)\
            .order_by(desc(RFPSubmission.created_at))\
            .offset(offset)\
            .limit(limit)\
            .all()
        
        return [submission.to_dict() for submission in submissions]
    
    def get_rfp_submission(self, rfp_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific RFP submission by ID"""
        
        submission = self.db.query(RFPSubmission).filter(RFPSubmission.id == rfp_id).first()
        return submission.to_dict() if submission else None
    
    def process_new_rfp(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Process a new RFP and find matching answers from existing submissions"""
        
        try:
            # Get all existing submissions for matching
            existing_submissions = self.get_all_rfp_submissions(limit=100)
            
            # Extract content from new RFP
            content = self.answer_extractor.document_processor.extract_text_from_file(file_path, filename)
            
            # Find matching answers
            matches = self.answer_matcher.find_matching_answers(content, existing_submissions)
            
            # Create a filled RFP response
            filled_response = self._create_filled_rfp_response(content, matches)
            
            return {
                "success": True,
                "filename": filename,
                "matches": matches,
                "filled_response": filled_response,
                "message": "RFP processed and answers suggested"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to process new RFP"
            }
    
    def _create_filled_rfp_response(self, original_content: str, matches: Dict[str, Any]) -> Dict[str, Any]:
        """Create a filled RFP response based on matches"""
        
        filled_response = {
            "original_content": original_content,
            "suggested_answers": [],
            "overall_confidence": matches.get("overall_confidence", 0),
            "generated_at": datetime.now().isoformat()
        }
        
        for match in matches.get("matches", []):
            if match.get("confidence", 0) > 50:  # Only include high-confidence matches
                filled_response["suggested_answers"].append({
                    "question": match.get("question", ""),
                    "answer": match.get("suggested_answer", ""),
                    "confidence": match.get("confidence", 0),
                    "source": match.get("source_rfp", ""),
                    "category": match.get("category", "general")
                })
        
        return filled_response
    
    def search_rfp_submissions(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search RFP submissions by content or company name"""
        
        # Simple text search - in production, you'd want to use full-text search
        submissions = self.db.query(RFPSubmission)\
            .filter(
                (RFPSubmission.original_content.contains(query)) |
                (RFPSubmission.company_name.contains(query)) |
                (RFPSubmission.filename.contains(query))
            )\
            .order_by(desc(RFPSubmission.created_at))\
            .limit(limit)\
            .all()
        
        return [submission.to_dict() for submission in submissions]
    
    def get_processing_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent processing jobs"""
        
        jobs = self.db.query(RFPProcessingJob)\
            .order_by(desc(RFPProcessingJob.created_at))\
            .limit(limit)\
            .all()
        
        return [job.to_dict() for job in jobs]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        
        total_submissions = self.db.query(RFPSubmission).count()
        processed_submissions = self.db.query(RFPSubmission).filter(RFPSubmission.is_processed == True).count()
        total_answers = self.db.query(RFPAnswer).count()
        
        # Get recent activity
        recent_submissions = self.db.query(RFPSubmission)\
            .order_by(desc(RFPSubmission.created_at))\
            .limit(5)\
            .all()
        
        return {
            "total_submissions": total_submissions,
            "processed_submissions": processed_submissions,
            "total_answers": total_answers,
            "processing_rate": (processed_submissions / total_submissions * 100) if total_submissions > 0 else 0,
            "recent_submissions": [sub.to_dict() for sub in recent_submissions]
        }
