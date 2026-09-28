@echo off

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
	echo Creating virtual environment...
	python -m venv venv
	if errorlevel 1 goto setup_failed
)

echo Checking and installing required packages...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto setup_failed

echo Checking Windows Firewall for TCP port 5000...
powershell -NoProfile -Command "$rule = Get-NetFirewallRule -DisplayName 'MTGTournamentFlask5000' -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq 'True' -and $_.Profile -match 'Private' -and $_.Profile -match 'Public' }; if ($rule) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
	echo Requesting permission to allow TCP port 5000 on Private and Public networks...
	powershell -NoProfile -Command "$rule = Get-NetFirewallRule -DisplayName 'MTGTournamentFlask5000' -ErrorAction SilentlyContinue; if ($rule) { $arguments = 'advfirewall firewall set rule name=MTGTournamentFlask5000 new enable=yes profile=private,public' } else { $arguments = 'advfirewall firewall add rule name=MTGTournamentFlask5000 dir=in action=allow protocol=TCP localport=5000 profile=private,public' }; try { $process = Start-Process -FilePath netsh.exe -Verb RunAs -Wait -PassThru -ArgumentList $arguments; exit $process.ExitCode } catch { exit 1 }"
	if errorlevel 1 (
		echo Could not update the firewall rule. The app will still start, but other devices may not be able to connect.
	) else (
		echo Firewall rule configured.
	)
)

"venv\Scripts\python.exe" app.py
goto end

:setup_failed
echo.
echo Failed to prepare Python dependencies. Check that Python is installed and try again.

:end

pause