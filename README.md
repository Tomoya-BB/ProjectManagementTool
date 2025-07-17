# Project Management Tool

This repository contains a simple web-based project management application built with Flask. It provides basic task management with Gantt chart and burndown visualization. All assets are served locally so the application can run in an offline environment.

## Features
- Add, edit and delete tasks
- Visualize tasks in a Gantt chart using Plotly
- Simple burndown chart
- Uses SQLite for storage
- Bootstrap 5 UI served from the local `static` folder

## Setup
1. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application
   ```bash
   python app.py
   ```
3. Open your browser at `http://localhost:5000`.

The database file `project.db` will be created automatically in the project directory.
