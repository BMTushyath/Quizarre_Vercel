@echo off
title Quizarre - Concurrency & Penalty Test
color 0B
echo ======================================================================
echo           QUIZARRE - CONCURRENCY & BUZZER PENALTY TEST
echo ======================================================================
echo.
echo Running test against: https://quizarre-vercel.onrender.com
echo.
python test_concurrency.py --url https://quizarre-vercel.onrender.com
echo.
echo ======================================================================
echo Test execution finished.
pause
