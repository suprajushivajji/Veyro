@echo off
cd /d "C:\Users\Supraj U Shivajji\Downloads\devhack\recoveros"

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker is not installed or not on PATH.
    echo Please install Docker Desktop for Windows, then reopen this terminal and run again.
    pause
    exit /b 1
)

echo Starting PostgreSQL...
docker compose up -d

if not exist ".venv" (
    echo Creating Python virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

 echo Creating database tables...
python scripts/create_tables.py

 echo Generating demo data...
python scripts/generate_data.py

 echo Seeding database...
python scripts/seed_database.py

 echo Starting backend...
start "VEYRO Backend" cmd /k "cd /d ""C:\Users\Supraj U Shivajji\Downloads\devhack\recoveros"" && call .venv\Scripts\activate.bat && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"

 echo Starting frontend...
cd /d "C:\Users\Supraj U Shivajji\Downloads\devhack\recoveros\apps\web"
start "VEYRO Frontend" cmd /k "cd /d ""C:\Users\Supraj U Shivajji\Downloads\devhack\recoveros\apps\web"" && npm run dev"

echo VEYRO is starting...
echo Backend URL: http://localhost:8000
echo Frontend URL: http://localhost:3000
pause
