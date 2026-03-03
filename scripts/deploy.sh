#!/bin/bash

# FusionPBX Analytics Dashboard - Production Deployment Script

set -e

echo "======================================"
echo "FusionPBX Analytics - Production Setup"
echo "======================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "\n${YELLOW}1. Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# Check .env file
echo -e "\n${YELLOW}2. Checking environment file...${NC}"

if [ ! -f .env ]; then
    echo -e "${RED}✗ .env file not found${NC}"
    echo "Create from .env.example:"
    echo "  cp .env.example .env"
    exit 1
fi
echo -e "${GREEN}✓ .env file exists${NC}"

# Verify required variables
REQUIRED_VARS=("FUSIONPBX_HOST" "FUSIONPBX_API_KEY" "DB_PASSWORD" "JWT_SECRET")
for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" .env; then
        echo -e "${RED}✗ Missing ${var} in .env${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ All required variables set${NC}"

# Check SSL certificates
echo -e "\n${YELLOW}3. Checking SSL certificates...${NC}"

if [ ! -f "docker/ssl/cert.pem" ] || [ ! -f "docker/ssl/key.pem" ]; then
    echo -e "${YELLOW}⚠ SSL certificates not found${NC}"
    echo "For production, please add:"
    echo "  - docker/ssl/cert.pem (certificate)"
    echo "  - docker/ssl/key.pem (private key)"
    echo ""
    echo "For Let's Encrypt:"
    echo "  sudo certbot certonly --standalone -d your-domain.com"
    echo "  sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/ssl/cert.pem"
    echo "  sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/ssl/key.pem"
else
    echo -e "${GREEN}✓ SSL certificates found${NC}"
fi

# Create volumes and networks
echo -e "\n${YELLOW}4. Creating Docker volumes and networks...${NC}"

docker network create analytics-network 2>/dev/null || true
echo -e "${GREEN}✓ Network ready${NC}"

# Pull latest images
echo -e "\n${YELLOW}5. Pulling latest Docker images...${NC}"

docker-compose pull || true
echo -e "${GREEN}✓ Images updated${NC}"

# Start services
echo -e "\n${YELLOW}6. Starting services...${NC}"

docker-compose up -d --no-build
echo -e "${GREEN}✓ Services starting${NC}"

# Wait for services to be ready
echo -e "\n${YELLOW}7. Waiting for services to be ready...${NC}"

for i in {1..60}; do
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend ready${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ Backend failed to start${NC}"
        exit 1
    fi
    echo -n "."
    sleep 1
done

# Run migrations
echo -e "\n${YELLOW}8. Running database migrations...${NC}"

docker-compose exec -T backend python -m scripts.init || {
    echo -e "${RED}✗ Migration failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Database initialized${NC}"

# Health check
echo -e "\n${YELLOW}9. Health checks...${NC}"

HEALTH_ENDPOINTS=(
    "http://localhost:8000/health"
    "http://localhost:3000"
)

for endpoint in "${HEALTH_ENDPOINTS[@]}"; do
    if curl -s -f "$endpoint" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $endpoint is healthy${NC}"
    else
        echo -e "${YELLOW}⚠ $endpoint may not be ready yet${NC}"
    fi
done

# Final summary
echo -e "\n${GREEN}======================================"
echo "Setup Complete!"
echo "======================================${NC}"
echo ""
echo "Services are running at:"
echo "  Frontend: https://localhost (or your domain)"
echo "  Backend API: https://localhost/api (or https://your-domain/api)"
echo "  API Docs: https://localhost/api/docs"
echo ""
echo "Default login:"
echo "  Username: admin"
echo "  Password: (from ADMIN_PASSWORD in .env)"
echo ""
echo "Next steps:"
echo "  1. Change admin password immediately"
echo "  2. Configure queues and agents in Admin Settings"
echo "  3. Set up scheduled reports"
echo "  4. Test data connection to FusionPBX"
echo ""
echo "For logs:"
echo "  docker-compose logs -f"
echo ""
echo "For support:"
echo "  - Check docs/RUNBOOK.md"
echo "  - Review logs: docker-compose logs"
echo "  - Test FusionPBX connection in Admin > ETL Status"
echo ""
