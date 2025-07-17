# Project Management Tool

This project is a small Flask based project management application. Tasks are stored per project in individual SQLite databases under `data/projects/` and global settings reside in `data/master.db`.
All required assets such as Bootstrap and Plotly are bundled inside the `static/` folder so the app works offline.

## Features
- Add, edit and delete tasks
- Gantt and burndown charts with Plotly
- Multiple project files selectable at start
- Milestone tasks with zero duration

## Setup
1. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application
   ```bash
   python app.py
   ```
3. Access `http://localhost:5000` and choose a project to start.
