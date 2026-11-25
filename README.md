# Diagnostic Window

Native Python / PySide6 industrial monitoring desktop application. Engineering baseline, not qualified for operational deployment.

## Run
Python 3.12: `python -m pip install -r requirements.txt`, then `python app.py`. Use isolated demo or create the first administrator. Run `python labview_mock.py` separately for local TCP verification. Mock data is not hardware data.

## LabVIEW
Python listens on 127.0.0.1:8767. Send a U32 big-endian length followed by UTF-8 JSON (max 1 MiB). Each full snapshot includes version: 1, increasing sequence, drives, io, modules and alarms. Drive fields include status, speed, torque, current, cw and sw (unsigned 16-bit words). I/O fields include status, value, raw, quality. Alarm objects require target, code, description and severity (WARN or FAULT). Optional cause and action provide guidance. No hardware writes. Local sender authentication remains pending.

## CI
[Windows build and verification](https://github.com/Robokks/Diagnostic-window-/actions) runs on push to main and manual dispatch. It executes core and offscreen GUI tests, compile checks, Bandit and pip-audit reports, and PyInstaller packaging. Security scans are reporting steps, not release gates. Download the complete SystemWindow-Windows-x64 artifact and extract the entire directory before launching SystemWindow.exe.

## Limitations
Exact HTML visual parity, hardware/telegram mapping, authenticated transport, long-duration testing and security remediation remain pending. Do not use as a safety function or deploy to operating equipment before validation.
