#!/bin/bash

# FusionPBX Analytics Dashboard - Development Setup Script

echo "======================================"
echo "FusionPBX Analytics - Development Setup"
echo "======================================"

cd "$(dirname "$0")/.."

# Create .env from template if needed
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠ Please edit .env with your FusionPBX credentials"
fi

# Create SSL directory
mkdir -p docker/ssl

# Generate self-signed certificate if needed
if [ ! -f docker/ssl/cert.pem ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -newkey rsa:4096 -nodes \
        -out docker/ssl/cert.pem \
        -keyout docker/ssl/key.pem \
        -days 365 \
        -subj "/CN=localhost"
    chmod 644 docker/ssl/cert.pem
    chmod 600 docker/ssl/key.pem
fi

# Start Docker Compose
echo "Starting Docker Compose..."
docker-compose down
docker-compose up -d

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Services running at:"
echo "  Frontend: http://localhost:3000"
echo "  Backend: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "View logs:"
echo "  docker-compose logs -f"
echo ""
echo "Initialize database (wait 10 seconds first):"
echo "  docker-compose exec backend python -m scripts.init"
echo "  docker-compose exec backend python -m scripts.seed"
echo ""
