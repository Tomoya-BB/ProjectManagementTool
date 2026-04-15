# Project Management Tool

This project is a small Flask based project management application. Tasks are stored per project in individual SQLite databases under `data/projects/` and global settings reside in `data/master.db`.
All required assets such as Bootstrap and Plotly are bundled inside the `static/` folder so the app works offline.

## Features
- Add, edit and delete tasks
- Update task progress with an intuitive slider
- Gantt chart with progress based coloring
- Burndown chart showing remaining work
- Multiple project files selectable at start
- Milestone tasks with zero duration

## Setup
1. Install dependencies
   ```bash
   ./.venv/bin/python -m pip install -r requirements.txt
   ```
2. Run the application
   ```bash
   ./run.sh
   ```
3. On first launch, you will be prompted to create an admin account.
4. Open the URL shown in the terminal. The app uses `http://localhost:5000` by default and automatically switches to the next open port if needed.

## Notes
- On recent macOS environments, `python` may not be available by default. Use `./run.sh` or `python3`.
- If you prefer to run directly without the helper script, use:
  ```bash
  ./.venv/bin/python app.py
  ```
