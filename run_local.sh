#!/bin/bash

# Local Development Runner Script
set -e

echo "🚀 Starting RFP Database locally..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please copy env.example to .env and configure your API keys"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check required environment variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY not set in .env file"
    exit 1
fi

echo "📋 Starting services..."

# Start PostgreSQL (if not running)
if ! pg_isready -q; then
    echo "🐘 Starting PostgreSQL..."
    if command -v brew &> /dev/null; then
        brew services start postgresql
    elif command -v systemctl &> /dev/null; then
        sudo systemctl start postgresql
    else
        echo "⚠️  Please start PostgreSQL manually"
    fi
fi

# Create database if it doesn't exist
echo "🗄️  Setting up database..."
createdb rfp_database 2>/dev/null || echo "Database may already exist"

# Install Python dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "🔄 Running database setup..."
python -c "
from app.database import create_tables
create_tables()
print('Database tables created successfully')
"

# Start the FastAPI server
echo "🌐 Starting FastAPI server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Wait a moment for the API to start
sleep 3

# Start Streamlit
echo "🎨 Starting Streamlit interface..."
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0 &
STREAMLIT_PID=$!

echo ""
echo "✅ RFP Database is running locally!"
echo ""
echo "📋 Access Points:"
echo "  - API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Streamlit UI: http://localhost:8501"
echo ""
echo "🔧 To stop the services, press Ctrl+C"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $API_PID 2>/dev/null || true
    kill $STREAMLIT_PID 2>/dev/null || true
    echo "✅ Services stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

# Wait for user to stop
wait
