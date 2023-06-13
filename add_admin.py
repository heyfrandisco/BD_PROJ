import psycopg2
import hashlib
import secrets
import re
import dotenv
import os
import utils

if __name__ == "__main__":

    # Load environment variables
    dotenv.load_dotenv()

    # Define new admin credentials
    #################################
    username = "admin1"
    password = "Password1!"
    email = "admin1@example.com"
    #################################

    # Verify fields
    if not utils.string_validate(username, max_len = 512):
        print("Invalid username! Expected string with length: 1 to 512")
        exit(1)
    if not utils.string_validate(password, max_len = 512):
        print("Invalid password! Expected string with length: 1 to 512")
        exit(1)
    if not utils.string_validate(email, max_len = 512):
        print("Invalid email! Expected string with length: 1 to 512")
        exit(1)

    if not utils.password_validate(password):
        print("Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!")
        exit(1)
    if not utils.email_validate(email):
        print("Invalid email!")
        exit(1)

    # Encrypt password
    password_salt = secrets.token_hex(16)
    password_pepper = os.environ.get("SECRET_KEY")
    password_hash  = hashlib.sha512((password + password_salt + password_pepper).encode("utf-8")).hexdigest()

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

    statement = """
            WITH inserted_user AS
            (
                INSERT INTO users (username, password_hash, password_salt, email)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            )
            INSERT INTO administrators (users_id)
            SELECT id FROM inserted_user
            RETURNING users_id
            """
    values = (username, password_hash, password_salt, email)

    try:
        cur.execute(statement, values)
        conn.commit()
        admin_id = cur.fetchone()[0]
        print(f"Admin added with ID {admin_id}!")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        print("Email or username already in use!")
        utils.db_disconnect(conn, cur)
        exit(1)
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        print(error)
        utils.db_disconnect(conn, cur)
        exit(1)

    finally:
        utils.db_disconnect(conn, cur)

    exit(0)
