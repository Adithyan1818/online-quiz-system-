# Online Quiz System

A web-based Online Quiz System built using:

- Python Flask
- MySQL
- HTML
- CSS
- JavaScript

## Main features

### User
- Registration
- Login/logout
- Dashboard
- Profile
- View published quizzes
- Attempt quiz
- Timer
- Automatic evaluation
- Score and percentage
- Previous results

### Admin
- Admin login
- Dashboard statistics
- Create quizzes
- Publish/disable quizzes
- Delete quizzes
- Add/delete questions
- View users
- View all results

## Setup

1. Install Python.
2. Install MySQL and start the MySQL server.
3. Open a terminal in this project folder.
4. Create a virtual environment:

   python -m venv venv

5. Activate it on Windows:

   venv\Scripts\activate

6. Install packages:

   pip install -r requirements.txt

7. Open `app.py` and change:

   YOUR_MYSQL_PASSWORD

   to your MySQL root password.

8. Open MySQL Workbench or MySQL command line.
9. Run all commands in `database.sql`.
10. Start the Flask application:

   python app.py

11. Open:

   http://127.0.0.1:5000

## Creating the first admin

Register a normal account through the website.

Then in MySQL run:

UPDATE users SET role = 'admin' WHERE email = 'your-email@example.com';

Then open:

http://127.0.0.1:5000/admin/login

and login with that account.

## Important

The secret key in `app.py` should be changed before real deployment.
