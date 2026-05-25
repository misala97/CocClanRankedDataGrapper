@echo off
setlocal

:: Check if a commit message was provided
if "%~1"=="" (
    echo Error: No commit message provided.
    echo Usage: sync.bat "Your commit message"
    exit /b 1
)

echo ==^> Adding files...
git add . || exit /b 1

echo ==^> Committing to dev...
git commit -m "%~1" || exit /b 1

echo ==^> Pushing dev...
git push || exit /b 1

echo ==^> Switching to main...
git checkout main || exit /b 1

echo ==^> Merging dev into main...
git merge dev || exit /b 1

echo ==^> Pushing main...
git push origin main || exit /b 1

echo ==^> Switching back to dev...
git checkout dev || exit /b 1

echo ==^> ✅ Successfully merged and pushed!