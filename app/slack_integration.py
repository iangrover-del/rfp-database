import os
import json
import tempfile
from typing import Dict, Any, Optional
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from app.services import RFPService
from app.document_processor import RFPAnswerExtractor
from sqlalchemy.orm import Session

class SlackRFPBot:
    """Slack bot for RFP database integration"""
    
    def __init__(self, db: Session):
        self.db = db
        self.slack_token = os.getenv("SLACK_BOT_TOKEN")
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        
        if self.slack_token:
            self.client = WebClient(token=self.slack_token)
        
        self.rfp_service = RFPService(db)
        self.answer_extractor = RFPAnswerExtractor(os.getenv("OPENAI_API_KEY"))
    
    def handle_file_upload(self, file_info: Dict[str, Any], channel_id: str) -> Dict[str, Any]:
        """Handle file upload from Slack"""
        
        try:
            # Download file from Slack
            file_url = file_info.get("url_private_download")
            filename = file_info.get("name", "unknown_file")
            
            if not file_url:
                return {"error": "No download URL provided"}
            
            # Download file content
            response = self.client.files_remote_info(file=file_info["id"])
            file_content = response["file"]["content"]
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            # Process the file
            if filename.lower().endswith(('.pdf', '.docx', '.xlsx', '.xls', '.txt')):
                # Check if this is a new RFP to process or historical to ingest
                result = self._process_slack_file(temp_file_path, filename, channel_id)
            else:
                result = {"error": "Unsupported file format"}
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            return result
            
        except Exception as e:
            return {"error": f"Failed to process file: {str(e)}"}
    
    def _process_slack_file(self, file_path: str, filename: str, channel_id: str) -> Dict[str, Any]:
        """Process uploaded file and determine if it's for ingestion or processing"""
        
        # For now, we'll process it as a new RFP to get suggestions
        # In a real implementation, you might want to ask the user
        result = self.rfp_service.process_new_rfp(file_path, filename)
        
        if result.get("success"):
            # Send results back to Slack
            self._send_rfp_results_to_slack(result, channel_id, filename)
            return {"success": True, "message": "RFP processed successfully"}
        else:
            return {"error": result.get("message", "Failed to process RFP")}
    
    def _send_rfp_results_to_slack(self, result: Dict[str, Any], channel_id: str, filename: str):
        """Send RFP processing results to Slack channel"""
        
        try:
            matches = result.get("matches", {})
            filled_response = result.get("filled_response", {})
            
            # Create message blocks
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📋 RFP Analysis Complete: {filename}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Overall Confidence:* {matches.get('overall_confidence', 0)}%"
                    }
                }
            ]
            
            # Add suggested answers
            suggested_answers = filled_response.get("suggested_answers", [])
            if suggested_answers:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Found {len(suggested_answers)} suggested answers:*"
                    }
                })
                
                for i, answer in enumerate(suggested_answers[:5]):  # Limit to first 5
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{i+1}. {answer.get('question', 'N/A')[:100]}...*\n"
                                   f"Answer: {answer.get('answer', 'N/A')[:200]}...\n"
                                   f"Confidence: {answer.get('confidence', 0)}% | "
                                   f"Source: {answer.get('source', 'N/A')}"
                        }
                    })
            
            # Add action buttons
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Full Results"
                        },
                        "action_id": "view_full_results",
                        "value": json.dumps({"filename": filename, "result": result})
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Download Filled RFP"
                        },
                        "action_id": "download_filled_rfp",
                        "value": json.dumps({"filename": filename, "filled_response": filled_response})
                    }
                ]
            })
            
            # Send message
            self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text=f"RFP Analysis Complete for {filename}"
            )
            
        except SlackApiError as e:
            print(f"Error sending message to Slack: {e.response['error']}")
    
    def handle_slash_command(self, command: str, text: str, user_id: str, channel_id: str) -> Dict[str, Any]:
        """Handle Slack slash commands"""
        
        if command == "/rfp-search":
            return self._handle_search_command(text, channel_id)
        elif command == "/rfp-stats":
            return self._handle_stats_command(channel_id)
        elif command == "/rfp-help":
            return self._handle_help_command(channel_id)
        else:
            return {"error": "Unknown command"}
    
    def _handle_search_command(self, query: str, channel_id: str) -> Dict[str, Any]:
        """Handle RFP search command"""
        
        if not query.strip():
            return {"error": "Please provide a search query"}
        
        try:
            results = self.rfp_service.search_rfp_submissions(query, limit=5)
            
            if results:
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🔍 Search Results for: {query}"
                        }
                    }
                ]
                
                for i, result in enumerate(results):
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{i+1}. {result.get('filename', 'N/A')}*\n"
                                   f"Company: {result.get('company_name', 'N/A')}\n"
                                   f"Created: {result.get('created_at', 'N/A')[:10]}"
                        }
                    })
                
                self.client.chat_postMessage(
                    channel=channel_id,
                    blocks=blocks,
                    text=f"Search results for: {query}"
                )
                
                return {"success": True, "message": f"Found {len(results)} results"}
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"No results found for: {query}"
                )
                return {"success": True, "message": "No results found"}
                
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    
    def _handle_stats_command(self, channel_id: str) -> Dict[str, Any]:
        """Handle RFP statistics command"""
        
        try:
            stats = self.rfp_service.get_statistics()
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 RFP Database Statistics"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Submissions:*\n{stats.get('total_submissions', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Processed:*\n{stats.get('processed_submissions', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Processing Rate:*\n{stats.get('processing_rate', 0):.1f}%"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Answers:*\n{stats.get('total_answers', 0)}"
                        }
                    ]
                }
            ]
            
            self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text="RFP Database Statistics"
            )
            
            return {"success": True, "message": "Statistics sent"}
            
        except Exception as e:
            return {"error": f"Failed to get statistics: {str(e)}"}
    
    def _handle_help_command(self, channel_id: str) -> Dict[str, Any]:
        """Handle help command"""
        
        help_text = """
🤖 *RFP Database Bot Commands*

*File Upload:*
• Upload any RFP document (PDF, DOCX, XLSX, TXT) to get AI-suggested answers

*Slash Commands:*
• `/rfp-search <query>` - Search existing RFP submissions
• `/rfp-stats` - View database statistics
• `/rfp-help` - Show this help message

*Features:*
• Automatic answer extraction from historical RFPs
• AI-powered matching for new RFP questions
• Confidence scoring for suggested answers
• Integration with your existing RFP database

*Supported File Formats:*
• PDF, DOCX, XLSX, XLS, TXT
        """
        
        self.client.chat_postMessage(
            channel=channel_id,
            text=help_text
        )
        
        return {"success": True, "message": "Help sent"}

def create_slack_app():
    """Create Slack app configuration"""
    
    return {
        "name": "RFP Database Bot",
        "description": "AI-powered RFP database integration",
        "features": {
            "bot_user": True,
            "slash_commands": [
                {
                    "command": "/rfp-search",
                    "description": "Search RFP submissions",
                    "usage_hint": "company name or keywords"
                },
                {
                    "command": "/rfp-stats",
                    "description": "View database statistics"
                },
                {
                    "command": "/rfp-help",
                    "description": "Show help information"
                }
            ],
            "event_subscriptions": [
                "file_shared"
            ],
            "oauth_scopes": [
                "channels:read",
                "chat:write",
                "files:read",
                "commands"
            ]
        }
    }
