@echo off
title Quizarre - 70 User Render Cloud Load Test
color 0A
echo ======================================================================
echo           QUIZARRE - 70 CONCURRENT USER LOAD TEST (RENDER)
echo ======================================================================
echo.
echo Testing 70 simultaneous WebSocket players on:
echo https://quizarre-vercel.onrender.com
echo.
python load_test.py --url https://quizarre-vercel.onrender.com --players 70 --duration 15
echo.
echo ======================================================================
echo Load test finished.
pause
