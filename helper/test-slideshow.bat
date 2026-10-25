@echo off
title Pulpit Binder slide show test
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0test-slideshow.ps1"
pause
