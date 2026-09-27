import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "online_quiz"),
    "port": int(os.getenv("DB_PORT", "3306"))
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect(url_for("register"))

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("Email already registered.", "error")
                return redirect(url_for("register"))

            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'user')",
                (name, email, password_hash)
            )
            db.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        finally:
            cursor.close()
            db.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, name, email, password_hash, role FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["name"] = user["name"]
                session["email"] = user["email"]
                session["role"] = user["role"]
                return redirect(url_for("dashboard"))

            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))
        finally:
            cursor.close()
            db.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT q.id, q.title, q.description, q.time_limit, q.status,
                   c.name AS category_name,
                   COUNT(qu.id) AS question_count
            FROM quizzes q
            LEFT JOIN categories c ON q.category_id = c.id
            LEFT JOIN questions qu ON q.id = qu.quiz_id
            WHERE q.status = 'published'
            GROUP BY q.id
            ORDER BY q.id DESC
        """)
        quizzes = cursor.fetchall()
        return render_template("dashboard.html", quizzes=quizzes)
    finally:
        cursor.close()
        db.close()


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name cannot be empty.", "error")
                return redirect(url_for("profile"))

            cursor.execute("UPDATE users SET name = %s WHERE id = %s",
                           (name, session["user_id"]))
            db.commit()
            session["name"] = name
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))

        cursor.execute(
            "SELECT id, name, email, role, created_at FROM users WHERE id = %s",
            (session["user_id"],)
        )
        user = cursor.fetchone()
        return render_template("profile.html", user=user)
    finally:
        cursor.close()
        db.close()


@app.route("/quiz/<int:quiz_id>")
@login_required
def quiz(quiz_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT q.id, q.title, q.description, q.time_limit,
                   c.name AS category_name
            FROM quizzes q
            LEFT JOIN categories c ON q.category_id = c.id
            WHERE q.id = %s AND q.status = 'published'
        """, (quiz_id,))
        quiz_data = cursor.fetchone()

        if not quiz_data:
            flash("Quiz not found or unavailable.", "error")
            return redirect(url_for("dashboard"))

        cursor.execute("""
            SELECT id, question_text, option_a, option_b, option_c, option_d, marks
            FROM questions
            WHERE quiz_id = %s
            ORDER BY id
        """, (quiz_id,))
        questions = cursor.fetchall()

        if not questions:
            flash("This quiz has no questions yet.", "error")
            return redirect(url_for("dashboard"))

        return render_template("quiz.html", quiz=quiz_data, questions=questions)
    finally:
        cursor.close()
        db.close()


@app.route("/submit_quiz/<int:quiz_id>", methods=["POST"])
@login_required
def submit_quiz(quiz_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, title
            FROM quizzes
            WHERE id = %s AND status = 'published'
        """, (quiz_id,))
        quiz_data = cursor.fetchone()

        if not quiz_data:
            flash("Quiz not found.", "error")
            return redirect(url_for("dashboard"))

        cursor.execute("""
            SELECT id, correct_option, marks
            FROM questions
            WHERE quiz_id = %s
            ORDER BY id
        """, (quiz_id,))
        questions = cursor.fetchall()

        score = 0
        total_marks = 0

        for q in questions:
            total_marks += q["marks"]
            selected = request.form.get(f"question_{q['id']}")
            if selected and selected == q["correct_option"]:
                score += q["marks"]

        percentage = round((score / total_marks) * 100, 2) if total_marks else 0

        cursor.execute("""
            INSERT INTO results
            (user_id, quiz_id, score, total_marks, percentage)
            VALUES (%s, %s, %s, %s, %s)
        """, (session["user_id"], quiz_id, score, total_marks, percentage))
        result_id = cursor.lastrowid
        db.commit()

        return redirect(url_for("result", result_id=result_id))
    finally:
        cursor.close()
        db.close()


@app.route("/result/<int:result_id>")
@login_required
def result(result_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.id, r.score, r.total_marks, r.percentage, r.attempted_at,
                   q.title AS quiz_title,
                   u.name AS user_name
            FROM results r
            JOIN quizzes q ON r.quiz_id = q.id
            JOIN users u ON r.user_id = u.id
            WHERE r.id = %s AND r.user_id = %s
        """, (result_id, session["user_id"]))
        result_data = cursor.fetchone()

        if not result_data:
            flash("Result not found.", "error")
            return redirect(url_for("dashboard"))

        return render_template("result.html", result=result_data)
    finally:
        cursor.close()
        db.close()


@app.route("/results")
@login_required
def previous_results():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.id, q.title AS quiz_title, r.score, r.total_marks,
                   r.percentage, r.attempted_at
            FROM results r
            JOIN quizzes q ON r.quiz_id = q.id
            WHERE r.user_id = %s
            ORDER BY r.attempted_at DESC
        """, (session["user_id"],))
        results = cursor.fetchall()
        return render_template("results.html", results=results)
    finally:
        cursor.close()
        db.close()


# ---------------- ADMIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT id, name, email, password_hash, role
                FROM users
                WHERE email = %s AND role = 'admin'
            """, (email,))
            admin = cursor.fetchone()

            if admin and check_password_hash(admin["password_hash"], password):
                session.clear()
                session["user_id"] = admin["id"]
                session["name"] = admin["name"]
                session["email"] = admin["email"]
                session["role"] = "admin"
                return redirect(url_for("admin_dashboard"))

            flash("Invalid admin credentials.", "error")
            return redirect(url_for("admin_login"))
        finally:
            cursor.close()
            db.close()

    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'user'")
        total_users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM quizzes")
        total_quizzes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM questions")
        total_questions = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM results")
        total_results = cursor.fetchone()["total"]

        return render_template(
            "admin_dashboard.html",
            total_users=total_users,
            total_quizzes=total_quizzes,
            total_questions=total_questions,
            total_results=total_results
        )
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes")
@admin_required
def admin_quizzes():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT q.id, q.title, q.description, q.time_limit, q.status,
                   c.name AS category_name,
                   COUNT(qu.id) AS question_count
            FROM quizzes q
            LEFT JOIN categories c ON q.category_id = c.id
            LEFT JOIN questions qu ON q.id = qu.quiz_id
            GROUP BY q.id
            ORDER BY q.id DESC
        """)
        quizzes = cursor.fetchall()

        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()

        return render_template(
            "admin_quizzes.html",
            quizzes=quizzes,
            categories=categories
        )
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes/create", methods=["POST"])
@admin_required
def create_quiz():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category_id = request.form.get("category_id")
    time_limit = request.form.get("time_limit", "10")
    status = request.form.get("status", "disabled")

    if not title or not category_id:
        flash("Title and category are required.", "error")
        return redirect(url_for("admin_quizzes"))

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO quizzes
            (title, description, category_id, time_limit, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            title, description, category_id, int(time_limit), status,
            session["user_id"]
        ))
        db.commit()
        flash("Quiz created.", "success")
        return redirect(url_for("admin_quizzes"))
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes/<int:quiz_id>/toggle", methods=["POST"])
@admin_required
def toggle_quiz(quiz_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE quizzes
            SET status = CASE
                WHEN status = 'published' THEN 'disabled'
                ELSE 'published'
            END
            WHERE id = %s
        """, (quiz_id,))
        db.commit()
        flash("Quiz status updated.", "success")
        return redirect(url_for("admin_quizzes"))
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes/<int:quiz_id>/delete", methods=["POST"])
@admin_required
def delete_quiz(quiz_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM quizzes WHERE id = %s", (quiz_id,))
        db.commit()
        flash("Quiz deleted.", "success")
        return redirect(url_for("admin_quizzes"))
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes/<int:quiz_id>/questions")
@admin_required
def manage_questions(quiz_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, title FROM quizzes WHERE id = %s", (quiz_id,))
        quiz_data = cursor.fetchone()

        if not quiz_data:
            flash("Quiz not found.", "error")
            return redirect(url_for("admin_quizzes"))

        cursor.execute("""
            SELECT id, question_text, option_a, option_b, option_c, option_d,
                   correct_option, marks
            FROM questions
            WHERE quiz_id = %s
            ORDER BY id
        """, (quiz_id,))
        questions = cursor.fetchall()

        return render_template(
            "manage_questions.html",
            quiz=quiz_data,
            questions=questions
        )
    finally:
        cursor.close()
        db.close()


@app.route("/admin/quizzes/<int:quiz_id>/questions/add", methods=["POST"])
@admin_required
def add_question(quiz_id):
    question_text = request.form.get("question_text", "").strip()
    option_a = request.form.get("option_a", "").strip()
    option_b = request.form.get("option_b", "").strip()
    option_c = request.form.get("option_c", "").strip()
    option_d = request.form.get("option_d", "").strip()
    correct_option = request.form.get("correct_option")
    marks = request.form.get("marks", "1")

    if not all([question_text, option_a, option_b, option_c, option_d, correct_option]):
        flash("All question fields are required.", "error")
        return redirect(url_for("manage_questions", quiz_id=quiz_id))

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO questions
            (quiz_id, question_text, option_a, option_b, option_c, option_d,
             correct_option, marks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            quiz_id, question_text, option_a, option_b, option_c, option_d,
            correct_option, int(marks)
        ))
        db.commit()
        flash("Question added.", "success")
        return redirect(url_for("manage_questions", quiz_id=quiz_id))
    finally:
        cursor.close()
        db.close()


@app.route("/admin/questions/<int:question_id>/delete", methods=["POST"])
@admin_required
def delete_question(question_id):
    quiz_id = request.form.get("quiz_id")

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM questions WHERE id = %s", (question_id,))
        db.commit()
        flash("Question deleted.", "success")
        return redirect(url_for("manage_questions", quiz_id=quiz_id))
    finally:
        cursor.close()
        db.close()


@app.route("/admin/users")
@admin_required
def manage_users():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, name, email, role, created_at
            FROM users
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()
        return render_template("manage_users.html", users=users)
    finally:
        cursor.close()
        db.close()


@app.route("/admin/results")
@admin_required
def admin_results():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.id, u.name AS user_name, u.email,
                   q.title AS quiz_title, r.score, r.total_marks,
                   r.percentage, r.attempted_at
            FROM results r
            JOIN users u ON r.user_id = u.id
            JOIN quizzes q ON r.quiz_id = q.id
            ORDER BY r.attempted_at DESC
        """)
        results = cursor.fetchall()
        return render_template("admin_results.html", results=results)
    finally:
        cursor.close()
        db.close()


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", message="Page not found."), 404


@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", message="Something went wrong on the server."), 500


if __name__ == "__main__":
    app.run(debug=True)
