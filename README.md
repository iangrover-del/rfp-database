# RFP Database System

An AI-powered RFP (Request for Proposal) database that automatically extracts answers from historical RFP submissions and suggests responses for new RFPs.

## 🚀 Features

- **Document Ingestion**: Upload historical RFP documents to build a knowledge base
- **AI-Powered Analysis**: Extract structured information from RFP documents using OpenAI GPT-4
- **Answer Matching**: Automatically match new RFP questions with existing answers
- **Confidence Scoring**: Rate the confidence of suggested answers
- **Multiple Formats**: Support for PDF, DOCX, XLSX, XLS, and TXT files
- **Web Interface**: Streamlit-based UI for easy interaction
- **API Access**: RESTful API for integration with other systems
- **Slack Integration**: Upload and process RFPs directly in Slack
- **AWS Deployment**: Cloud-native deployment with auto-scaling

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Streamlit UI  │    │   FastAPI API   │    │   Slack Bot     │
│   (Port 8501)   │    │   (Port 8000)   │    │   Integration   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │   Database      │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │   AWS S3        │
                    │   Document      │
                    │   Storage       │
                    └─────────────────┘
```

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- AWS CLI configured
- OpenAI API key

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd rfp-database
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys and configuration
   ```

4. **Start with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

5. **Access the application**:
   - API: http://localhost:8000
   - Streamlit UI: http://localhost:8501
   - API Documentation: http://localhost:8000/docs

### AWS Deployment

1. **Set environment variables**:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   export AWS_ACCESS_KEY_ID="your-aws-access-key"
   export AWS_SECRET_ACCESS_KEY="your-aws-secret-key"
   export AWS_REGION="us-east-1"
   ```

2. **Deploy to AWS**:
   ```bash
   ./deploy.sh
   ```

The deployment script will:
- Create an S3 bucket for document storage
- Deploy a PostgreSQL RDS database
- Build and push Docker images to ECR
- Deploy the application using ECS Fargate
- Set up an Application Load Balancer

## 📖 Usage

### 1. Building Your Knowledge Base

Upload historical RFP documents to build your knowledge base:

```bash
# Using the API
curl -X POST "http://localhost:8000/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@historical_rfp.pdf"

# Using the Streamlit UI
# Navigate to "Upload RFP" page and upload files
```

### 2. Processing New RFPs

Upload a new RFP to get AI-suggested answers:

```bash
# Using the API
curl -X POST "http://localhost:8000/process" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@new_rfp.pdf"

# Using the Streamlit UI
# Navigate to "Process New RFP" page and upload files
```

### 3. API Endpoints

- `POST /upload` - Upload and ingest RFP documents
- `POST /process` - Process new RFP and get suggestions
- `GET /submissions` - List all RFP submissions
- `GET /submissions/{id}` - Get specific submission details
- `GET /search?q=query` - Search submissions
- `GET /statistics` - Get database statistics
- `GET /health` - Health check

### 4. Slack Integration

1. Create a Slack app at https://api.slack.com/apps
2. Configure the following:
   - Bot Token Scopes: `channels:read`, `chat:write`, `files:read`, `commands`
   - Event Subscriptions: `file_shared`
   - Slash Commands: `/rfp-search`, `/rfp-stats`, `/rfp-help`
3. Set environment variables:
   ```bash
   export SLACK_BOT_TOKEN="xoxb-your-bot-token"
   export SLACK_SIGNING_SECRET="your-signing-secret"
   ```

## 🔧 Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=your_openai_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key

# Optional
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-rfp-bucket
DATABASE_URL=postgresql://user:pass@localhost:5432/rfp_database
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your_slack_signing_secret
```

### Database Schema

The system uses three main tables:

- `rfp_submissions`: Stores uploaded RFP documents and extracted data
- `rfp_answers`: Stores standardized answers from historical submissions
- `rfp_processing_jobs`: Tracks processing status and progress

## 🧪 Testing

```bash
# Run tests
python -m pytest tests/

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/statistics
```

## 📊 Monitoring

The application includes:

- Health check endpoint (`/health`)
- Processing job tracking
- Database statistics
- CloudWatch logs (AWS deployment)

## 🔒 Security

- All file uploads are validated
- Database credentials are managed securely
- S3 buckets have proper access controls
- API endpoints include input validation

## 🚀 Scaling

The AWS deployment includes:

- Auto-scaling ECS services
- Load balancer for high availability
- RDS with automated backups
- S3 for scalable document storage

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For support and questions:

1. Check the API documentation at `/docs`
2. Review the logs for error details
3. Open an issue on GitHub

## 🔄 Updates

To update the deployment:

```bash
# Pull latest changes
git pull origin main

# Redeploy
./deploy.sh
```

The system will automatically update with zero downtime.
