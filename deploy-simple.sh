#!/bin/bash

# Simplified RFP Database Deployment Script
set -e

echo "🚀 Starting simplified RFP Database deployment..."

# Check if required environment variables are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable is required"
    exit 1
fi

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "❌ Error: AWS credentials are required"
    exit 1
fi

# Set default values
AWS_REGION=${AWS_REGION:-us-east-1}
S3_BUCKET_NAME=${S3_BUCKET_NAME:-rfp-database-$(date +%s)}
STACK_NAME=${STACK_NAME:-rfp-database}

echo "📋 Deployment Configuration:"
echo "  - AWS Region: $AWS_REGION"
echo "  - S3 Bucket: $S3_BUCKET_NAME"
echo "  - Stack Name: $STACK_NAME"

# Create S3 bucket for CloudFormation templates
echo "📦 Creating S3 bucket for deployment artifacts..."
aws s3 mb s3://$S3_BUCKET_NAME --region $AWS_REGION || echo "Bucket may already exist"

# Build and push Docker image to ECR
echo "🐳 Building and pushing Docker image..."

# Get ECR login token
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com

# Build Docker image
docker build -t rfp-database-repo .

# Tag and push image
ECR_URI=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com/rfp-database-repo:latest
docker tag rfp-database-repo:latest $ECR_URI
docker push $ECR_URI

echo "✅ Docker image pushed to ECR"

# Deploy CloudFormation stack
echo "☁️  Deploying CloudFormation stack..."

# Generate random database password
DB_PASSWORD=$(openssl rand -base64 32)

aws cloudformation deploy \
    --template-file aws-deploy-simple.yml \
    --stack-name $STACK_NAME \
    --parameter-overrides \
        OpenAIApiKey=$OPENAI_API_KEY \
        DatabasePassword=$DB_PASSWORD \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION

echo "✅ CloudFormation stack deployed"

# Get stack outputs
echo "📊 Getting deployment information..."
APPLICATION_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ApplicationURL`].OutputValue' \
    --output text)

DATABASE_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`DatabaseEndpoint`].OutputValue' \
    --output text)

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Deployment Summary:"
echo "  - Application URL: $APPLICATION_URL"
echo "  - Database Endpoint: $DATABASE_ENDPOINT"
echo "  - S3 Bucket: $S3_BUCKET_NAME"
echo ""
echo "🔧 Next Steps:"
echo "  1. Wait 5-10 minutes for the application to fully start"
echo "  2. Visit $APPLICATION_URL to access the RFP Database"
echo "  3. Upload your historical RFP documents to build the knowledge base"
echo ""
echo "📚 Documentation:"
echo "  - API Documentation: $APPLICATION_URL/docs"
echo ""
echo "🔐 Database Credentials:"
echo "  - Username: rfp_user"
echo "  - Password: $DB_PASSWORD"
echo "  - Endpoint: $DATABASE_ENDPOINT"
echo ""
echo "⚠️  Important: Save the database password securely!"
