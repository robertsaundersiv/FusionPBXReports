@echo off
REM FusionPBX Analytics Dashboard - Windows Development Setup

echo ======================================
echo FusionPBX Analytics - Windows Setup
echo ======================================
echo.

REM Create .env from template if needed
if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit .env with your FusionPBX credentials
    pause
)

REM Create SSL directory
if not exist "docker\ssl" mkdir docker\ssl

REM Generate self-signed certificate if needed
if not exist "docker\ssl\cert.pem" (
    echo.
    echo Generating self-signed SSL certificate...
    echo Note: If this fails, you may need OpenSSL installed
    echo For Windows, use: choco install openssl or download from https://slproweb.com/products/Win32OpenSSL.html
    
    REM Try OpenSSL if available
    where openssl >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        openssl req -x509 -newkey rsa:4096 -nodes ^
            -out docker\ssl\cert.pem ^
            -keyout docker\ssl\key.pem ^
            -days 365 ^
            -subj "/CN=localhost"
    ) else (
        echo.
        echo WARNING: OpenSSL not found. Please manually create certificates or install OpenSSL.
        echo For development, TLS is not strictly required.
    )
)

REM Start Docker Compose
echo.
echo Starting Docker Compose...
docker compose down
docker compose up -d

echo.
echo ======================================
echo Setup Complete!
echo ======================================
echo.
echo Services running at:
echo   Frontend: http://localhost:3000
echo   Backend: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo To view logs:
echo   docker compose logs -f
echo.
echo To initialize database (after services start):
echo   docker compose exec backend python -m scripts.init
echo   docker compose exec backend python -m scripts.seed
echo.
pause
