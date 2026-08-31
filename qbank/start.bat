@echo off
REM QBank Quick Start Script for Windows
REM Run this to start both backend and frontend

echo.
echo 🚀 QBank Quick Start
echo ====================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js not found. Please install Node.js 18+
    pause
    exit /b 1
)

REM Start Backend in new window
echo 📦 Starting Backend...
cd backend

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('uvicorn') else 1)" >nul 2>&1
if errorlevel 1 (
    echo Installing Python dependencies...
    pip install -q -r requirements.txt
    type nul > .installed
) else if not exist ".installed" (
    type nul > .installed
)

echo ✅ Backend starting on http://127.0.0.1:8000
start cmd /k "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

cd ..

REM Start Frontend in new window
echo.
echo 🎨 Starting Frontend...
cd frontend

if not exist "node_modules" (
    echo Installing npm dependencies...
    call npm install --quiet
)

echo ✅ Frontend starting on http://localhost:5173
start cmd /k "npm run dev"

cd ..

echo.
echo ====================
echo 🎉 QBank is running!
echo.
echo 📚 Backend (API):   http://127.0.0.1:8000
echo 📖 API Docs:        http://127.0.0.1:8000/docs
echo 🎨 Frontend:        http://localhost:5173
echo.
echo 🤖 AI Configuration:
echo    Current: Check backend\.env
echo    Options: ollama (local, free) or openai (cloud, requires key)
echo.
echo 📝 Demo Login:
echo    Email: admin@qbank.vn
echo    Password: Admin@123
echo.
echo Both backend and frontend are running in separate windows.
echo Close the windows to stop the servers.
echo ====================
echo.
pause
