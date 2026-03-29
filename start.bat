@echo off
echo 🚀 Initializing CirbuildSTG Environment...

:: 1. Create a virtual environment if it doesn't exist
if not exist "venv\" (
    echo 📦 Creating a fresh virtual environment...
    python -m venv venv
)

:: 2. Activate the virtual environment
call venv\Scripts\activate.bat

:: 3. Ensure core build tools are up to date
python -m pip install --upgrade pip setuptools wheel

:: 4. Force-fetch the absolute latest Spec2RTL from the remote main branch
::    --force-reinstall --no-cache-dir bypasses pip's git cache so you
::    always get the newest commit, not a cached version.
echo 🔄 Fetching the latest Spec2RTL from remote...
pip install --upgrade --force-reinstall --no-cache-dir git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main

:: 5. Install local project and remaining dependencies safely
echo 🛠️ Installing CirbuildSTG dependencies...
pip install -r requirements.txt
pip install -e .

:: 6. Launch the application
echo ✨ Launching CirbuildSTG...
cirbuild
pause
