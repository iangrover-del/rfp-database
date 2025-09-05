import boto3
import os
from typing import Optional
from botocore.exceptions import ClientError
import uuid
from datetime import datetime

class S3Storage:
    """Handles file storage and retrieval from AWS S3"""
    
    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
    
    def upload_file(self, file_path: str, filename: str) -> str:
        """Upload a file to S3 and return the S3 key"""
        
        # Generate unique S3 key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        s3_key = f"rfp-documents/{timestamp}_{unique_id}_{filename}"
        
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key)
            return s3_key
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {str(e)}")
    
    def download_file(self, s3_key: str, local_path: str) -> bool:
        """Download a file from S3 to local storage"""
        
        try:
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            return True
        except ClientError as e:
            print(f"Failed to download file from S3: {str(e)}")
            return False
    
    def delete_file(self, s3_key: str) -> bool:
        """Delete a file from S3"""
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            print(f"Failed to delete file from S3: {str(e)}")
            return False
    
    def get_file_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for file access"""
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            print(f"Failed to generate presigned URL: {str(e)}")
            return None
    
    def list_files(self, prefix: str = "rfp-documents/") -> list:
        """List all files in the S3 bucket with given prefix"""
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
            
            return files
        except ClientError as e:
            print(f"Failed to list files: {str(e)}")
            return []

class DocumentStorage:
    """High-level document storage interface"""
    
    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        self.s3_storage = S3Storage(bucket_name, region)
    
    def store_rfp_document(self, file_path: str, filename: str) -> dict:
        """Store an RFP document and return storage info"""
        
        # Upload to S3
        s3_key = self.s3_storage.upload_file(file_path, filename)
        
        # Generate access URL
        access_url = self.s3_storage.get_file_url(s3_key)
        
        return {
            "s3_key": s3_key,
            "access_url": access_url,
            "filename": filename,
            "stored_at": datetime.now().isoformat()
        }
    
    def retrieve_rfp_document(self, s3_key: str, local_path: str) -> bool:
        """Retrieve an RFP document from storage"""
        return self.s3_storage.download_file(s3_key, local_path)
    
    def cleanup_temp_file(self, s3_key: str) -> bool:
        """Remove a document from storage"""
        return self.s3_storage.delete_file(s3_key)
