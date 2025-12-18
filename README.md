# Event Scheduling & Resource Allocation System

A simple Flask + MySQL web application to create events, manage shared resources, and allocate resources without time conflicts.

This project focuses on handling overlapping time intervals and tracking resource usage.

## Features
- Add, edit and view events
- Add, edit and view resources
- Allocate resources to events
- Prevent double booking of resources
- Safe deletion (blocked if already allocated)
- Resource utilisation report for a selected date range
- Download utilisation report as PDF

## Tech Stack
- Python (Flask)
- MySQL
- HTML, Bootstrap
- xhtml2pdf

## How to Run
1. Create a MySQL database named `event_scheduler`
2. Install dependencies:
   `pip install -r requirements.txt`
3. Run the app  
   `python app.py`
4. Open `http://127.0.0.1:5000`