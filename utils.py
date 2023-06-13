import datetime
import flask
import re
import os
import psycopg2

StatusCodes = {
                "success": 200,
                "bad_request": 400,
                "unauthorized": 401,
                "forbidden": 403,
                "page_not_found": 404,
                "method_not_allowed": 405,
                "too_many_requests": 429,
                "internal_error": 500,
                "not_implemented": 501,
            }

def db_connect():
    conn = psycopg2.connect(
        database = os.environ.get("DB_NAME"),
        user = os.environ.get("DB_USER"),
        password = os.environ.get("DB_PASSWORD"),
        host = os.environ.get("DB_HOST"),
        port = os.environ.get("DB_PORT")
    )
    if not conn:
        flask.abort(StatusCodes["internal_error"], "Could not connect to the database!")
    else:
        return conn, conn.cursor()

def db_disconnect(conn, cur):
    if conn:
        # Always rollback changes before disconnecting, if they are already committed or there is no transaction this will do nothing
        conn.rollback()
        cur.close()
        conn.close()

def payload_validate(payload, required):
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        flask.abort(StatusCodes["bad_request"], f"Missing fields in JSON payload: {difference}")

def string_to_int(string):
    try:
        return int(string)
    except ValueError:
        return None

def string_validate(string, min_len = 1, max_len = None, only_digits = False):
    if isinstance(string, str):
        if only_digits and not string.isdigit():
            return False
        if min_len is not None and len(string) < min_len:
            return False
        if max_len is not None and len(string) > max_len:
            return False
        return True
    return False

def integer_validate(integer, min_val = None, max_val = None):
    if isinstance(integer, int):
        if min_val is not None and integer < min_val:
            return False
        if max_val is not None and integer > max_val:
            return False
        return True
    return False

def boolean_validate(boolean):
    if isinstance(boolean, bool):
        return True
    return False

def list_validate(array, min_len = None, max_len = None):
    if isinstance(array, list):
        if min_len is not None and len(array) < min_len:
            return False
        if max_len is not None and len(array) > max_len:
            return False
        return True
    return False

def datetime_validate(date, format, future = False, past = False):
    try:
        date = datetime.datetime.strptime(date, format)
        if future and past:
            # Allows both future and past dates, always true if valid format
            return True
        if future and date < datetime.datetime.now():
            return False
        if past and date > datetime.datetime.now():
            return False
        return True
    except ValueError:
        return False

def password_validate(password):
    if not re.match(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*\W).{8,}$", password):
        return False
    return True

def email_validate(email):
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        return False
    return True

def get_request_ip():
    proxied_ip = flask.request.environ.get('HTTP_X_FORWARDED_FOR')
    if not proxied_ip:
        ip = flask.request.environ.get('REMOTE_ADDR')
        if not ip:
            return "Not Found"
        return ip
    else:
        return proxied_ip