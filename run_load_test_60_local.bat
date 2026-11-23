@echo off
title Quizarre - 70 User Local Load Test
color 0E
echo ======================================================================
echo           QUIZARRE - 70 CONCURRENT USER LOAD TEST (LOCAL)
echo ======================================================================
echo.
echo Testing 70 simultaneous WebSocket players on:
echo http://localhost:8000
echo.
python load_test.py --url http://localhost:8000 --players 70 --duration 15
echo.
echo ======================================================================
echo Load test finished.
pause
