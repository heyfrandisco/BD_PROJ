# MANUALLY ADD ADMINS

import psycopg2
import datetime
import hashlib
import re
import dotenv
import os

if __name__ == "__main__":

    # Load environment variables
    dotenv.load_dotenv()

    # Connect to the database
    conn = psycopg2.connect(
        database = os.environ.get("DB_NAME"),
        user = os.environ.get("DB_USER"),
        password = os.environ.get("DB_PASSWORD"),
        host = os.environ.get("DB_HOST"),
        port = os.environ.get("DB_PORT")
    )
    if conn is None:
        print("Could not connect to the database!")
        exit(1)
    cur = conn.cursor()

    # SET NEW ADMIN CREDENCIALS HERE
    #################################
    username = "admin1"
    password = "Password1!"
    email = "admin1@example.com"
    birthday = "1993-10-04"
    #################################

    # Verify that the username meets the requirements
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        print("Username can only contain letters, numbers and underscores!")
        exit(1)
    # Verify that the password meets the requirements
    if not re.match(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*\W).{8,}$", password):
        print("Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!")
        exit(1)
    # Verify that the email is in the correct format
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        print("Invalid email!")
        exit(1)
    # Verify that the birthday is in the correct format
    try:
        datetime.datetime.strptime(birthday, "%Y-%m-%d")
    except ValueError:
        print("Invalid birthday format! Expected: YYYY-MM-DD")


    # Encrypt password
    salt = os.environ.get("SERVER_SECRET_KEY")
    password  = hashlib.sha256((password + salt).encode()).hexdigest()
    statement = """
            WITH inserted_user AS
            (
                INSERT INTO users (username, password, email, birthday)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            )
            INSERT INTO administrators (users_id)
            SELECT id FROM inserted_user
            """
    values = (username, password, email, birthday)

    try:
        cur.execute(statement, values)
        conn.commit()
        print(f"Admin {username} added!")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        print("Email or username already in use!")
        exit(1)
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        print(error)
        exit(1)

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    exit(0)
