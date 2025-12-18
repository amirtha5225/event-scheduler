import os

from flask import Flask, render_template, request, redirect, url_for
import mysql.connector
from xhtml2pdf import pisa
from io import BytesIO
from datetime import datetime
from flask import Response

app = Flask(__name__)
app.secret_key = "event_scheduler_secret_key"


# ---------- DATABASE CONNECTION ----------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "event_scheduler")
    )

# ---------- HOME ----------
@app.route("/")
def home():
    return redirect(url_for("events"))

# ---------- RESOURCES ----------
@app.route("/resources", methods=["GET", "POST"])
def resources():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["resource_name"]
        rtype = request.form["resource_type"]

        cursor.execute(
            "INSERT INTO Resource (resource_name, resource_type) VALUES (%s, %s)",
            (name, rtype)
        )
        conn.commit()
        return redirect(url_for("resources"))

    cursor.execute("SELECT * FROM Resource")
    resources = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("resources.html", resources=resources)

# ---------- EDIT RESOURCE ----------
@app.route("/resources/edit/<int:resource_id>", methods=["GET", "POST"])
def edit_resource(resource_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM Resource WHERE resource_id=%s", (resource_id,))
    resource = cursor.fetchone()

    if request.method == "POST":
        name = request.form["resource_name"]
        rtype = request.form["resource_type"]

        cursor.execute(
            "UPDATE Resource SET resource_name=%s, resource_type=%s WHERE resource_id=%s",
            (name, rtype, resource_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("resources"))

    cursor.close()
    conn.close()
    return render_template("edit_resource.html", resource=resource)

# ---------- EVENTS ----------
@app.route("/events", methods=["GET", "POST"])
def events():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO Event (title, start_time, end_time, description)
            VALUES (%s, %s, %s, %s)
        """, (
            request.form["title"],
            request.form["start_time"],
            request.form["end_time"],
            request.form["description"]
        ))
        conn.commit()
        return redirect(url_for("events"))

    cursor.execute("SELECT * FROM Event ORDER BY start_time")
    events = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("events.html", events=events)

# ---------- EDIT EVENT ----------
@app.route("/events/edit/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM Event WHERE event_id=%s", (event_id,))
    event = cursor.fetchone()

    if request.method == "POST":
        title = request.form["title"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        description = request.form["description"]

        # Conflict recheck
        cursor.execute("""
            SELECT r.resource_name, e.title
            FROM Event e
            JOIN EventResourceAllocation a ON e.event_id = a.event_id
            JOIN Resource r ON r.resource_id = a.resource_id
            WHERE a.resource_id IN (
                SELECT resource_id FROM EventResourceAllocation WHERE event_id=%s
            )
            AND e.event_id != %s
            AND (%s < e.end_time AND %s > e.start_time)
        """, (event_id, event_id, start_time, end_time))

        conflict = cursor.fetchone()
        if conflict:
            event.update({
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "description": description
            })
            error = f"Conflict with event '{conflict['title']}' for resource '{conflict['resource_name']}'"
            return render_template("edit_event.html", event=event, error=error)

        cursor.execute("""
            UPDATE Event
            SET title=%s, start_time=%s, end_time=%s, description=%s
            WHERE event_id=%s
        """, (title, start_time, end_time, description, event_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("events"))

    cursor.close()
    conn.close()
    return render_template("edit_event.html", event=event)

# ---------- ALLOCATE ----------
@app.route("/allocate", methods=["GET", "POST"])
def allocate():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    error = None

    if request.method == "POST":
        event_id = request.form["event_id"]
        resource_id = request.form["resource_id"]

        cursor.execute(
            "SELECT start_time, end_time FROM Event WHERE event_id=%s",
            (event_id,)
        )
        event = cursor.fetchone()

        cursor.execute("""
            SELECT e.title
            FROM Event e
            JOIN EventResourceAllocation a ON e.event_id = a.event_id
            WHERE a.resource_id=%s
            AND (%s < e.end_time AND %s > e.start_time)
        """, (resource_id, event["start_time"], event["end_time"]))

        conflict = cursor.fetchone()
        if conflict:
            error = f"Conflict! Resource already booked for event '{conflict['title']}'"
        else:
            cursor.execute("""
                INSERT INTO EventResourceAllocation (event_id, resource_id)
                VALUES (%s, %s)
            """, (event_id, resource_id))
            conn.commit()
            return redirect(url_for("allocate"))

    cursor.execute("SELECT * FROM Event")
    events = cursor.fetchall()

    cursor.execute("SELECT * FROM Resource")
    resources = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("allocate.html", events=events, resources=resources, error=error)

# ---------- REPORT ----------
@app.route("/report", methods=["GET", "POST"])
def report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    report_data = []

    if request.method == "POST":
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]

        cursor.execute("SELECT * FROM Resource")
        resources = cursor.fetchall()

        for r in resources:
            cursor.execute("""
                SELECT start_time, end_time
                FROM Event e
                JOIN EventResourceAllocation a ON e.event_id = a.event_id
                WHERE a.resource_id=%s
                AND e.start_time >= %s
                AND e.end_time <= %s
            """, (r["resource_id"], start_date, end_date))

            events = cursor.fetchall()
            total_hours = sum(
                (e["end_time"] - e["start_time"]).total_seconds() / 3600
                for e in events
            )

            cursor.execute("""
                SELECT COUNT(*) AS count
                FROM Event e
                JOIN EventResourceAllocation a ON e.event_id = a.event_id
                WHERE a.resource_id=%s
                AND e.start_time > NOW()
            """, (r["resource_id"],))

            upcoming = cursor.fetchone()["count"]

            report_data.append({
                "resource": r["resource_name"],
                "hours": round(total_hours, 2),
                "upcoming": upcoming
            })

    cursor.close()
    conn.close()
    return render_template("report.html", report=report_data)

@app.route("/report/pdf")
def report_pdf():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not start_date or not end_date:
        return "Please generate the report before downloading PDF", 400

    generated_on = datetime.now().strftime("%d %b %Y, %I:%M %p")

    cursor.execute("SELECT * FROM Resource")
    resources = cursor.fetchall()

    report = []
    total_hours_all = 0

    for r in resources:
        cursor.execute("""
            SELECT e.start_time, e.end_time
            FROM Event e
            JOIN EventResourceAllocation a ON e.event_id = a.event_id
            WHERE a.resource_id = %s
            AND e.start_time >= %s
            AND e.end_time <= %s
        """, (r["resource_id"], start_date, end_date))

        events = cursor.fetchall()
        total_hours = sum(
            (e["end_time"] - e["start_time"]).total_seconds() / 3600
            for e in events
        )

        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Event e
            JOIN EventResourceAllocation a ON e.event_id = a.event_id
            WHERE a.resource_id = %s
            AND e.start_time > NOW()
        """, (r["resource_id"],))

        upcoming = cursor.fetchone()["count"]

        if total_hours > 0 or upcoming > 0:
            report.append({
                "resource": r["resource_name"],
                "hours": round(total_hours, 2),
                "upcoming": upcoming
            })
            total_hours_all += total_hours

    summary = {
        "total_resources": len(report),
        "total_hours": round(total_hours_all, 2)
    }

    cursor.close()
    conn.close()

    html = render_template(
        "report_pdf.html",
        report=report,
        summary=summary,
        start_date=start_date,
        end_date=end_date,
        generated_on=generated_on
    )

    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)

    if pisa_status.err:
        return "PDF generation failed", 500

    return Response(
        result.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=resource_utilisation_report.pdf"
        }
    )
from flask import flash

@app.route("/events/delete/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM EventResourceAllocation WHERE event_id=%s",
        (event_id,)
    )
    used = cursor.fetchone()["cnt"]

    if used > 0:
        flash("Cannot delete event. Resources are already allocated.", "danger")
    else:
        cursor.execute("DELETE FROM Event WHERE event_id=%s", (event_id,))
        conn.commit()
        flash("Event deleted successfully.", "success")

    cursor.close()
    conn.close()
    return redirect(url_for("events"))

@app.route("/resources/delete/<int:resource_id>", methods=["POST"])
def delete_resource(resource_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM EventResourceAllocation WHERE resource_id=%s",
        (resource_id,)
    )
    used = cursor.fetchone()["cnt"]

    if used > 0:
        flash("Cannot delete resource. It is allocated to events.", "danger")
    else:
        cursor.execute("DELETE FROM Resource WHERE resource_id=%s", (resource_id,))
        conn.commit()
        flash("Resource deleted successfully.", "success")

    cursor.close()
    conn.close()
    return redirect(url_for("resources"))


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)
