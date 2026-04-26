@echo off
REM pushit.bat - Commit and push all changes with a fixed message (project-local)

git add .
git commit -m "pushit: quick sync commit"
git push origin main
