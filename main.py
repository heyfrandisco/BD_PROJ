import flask
import logging
import psycopg2
import datetime
import hashlib
import jwt
import re
import random
import dotenv
import os
import functools

app = flask.Flask(__name__)

def db_connect():
    conn = psycopg2.connect(
        database = os.environ.get("DB_NAME"),
        user = os.environ.get("DB_USER"),
        password = os.environ.get("DB_PASSWORD"),
        host = os.environ.get("DB_HOST"),
        port = os.environ.get("DB_PORT")
    )
    return conn

def requires_token(restrict):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            token = flask.request.headers.get("JWT-Token")

            if token is None:
                response = {"status": StatusCodes["bad_request"], "errors": "This action requires you to be authenticated!"}
                return flask.jsonify(response)
            try:
                token_info = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                response = {"status": StatusCodes["bad_request"], "errors": "Your token has expired, authenticate again!"}
                return flask.jsonify(response)
            except jwt.InvalidTokenError:
                response = {"status": StatusCodes["bad_request"], "errors": "Invalid token, authenticate again!"}
                return flask.jsonify(response)

            # Check if user has acess to the endpoint, must be in the restrict table passed as argument
            user_id = token_info["user_id"]

            if restrict == "consumers_regular":
                statement = "SELECT EXISTS(SELECT 1 FROM consumers WHERE users_id = %s)"
            elif restrict == "consumers_premium":
                statement = "SELECT EXISTS(SELECT 1 FROM subscriptions WHERE consumers_users_id = %s AND end_date >= CURRENT_DATE)"
            elif restrict == "artists":
                statement = "SELECT EXISTS(SELECT 1 FROM artists WHERE users_id = %s)"
            elif restrict == "administrators":
                statement = "SELECT EXISTS(SELECT 1 FROM administrators WHERE users_id = %s)"
            else:
                response = {"status": StatusCodes["internal_error"], "errors": "Invalid role restriction in this endpoint!"}
                return flask.jsonify(response)
            values = (user_id,)

            conn = db_connect()
            if conn is None:
                response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
                return flask.jsonify(response)
            cur = conn.cursor()

            try:
                cur.execute(statement,values)
                result = cur.fetchone()
                permitted = result[0]
                if not permitted:
                    response = {"status": StatusCodes["bad_request"], "errors": "You lack the required role this action!"}
                    return flask.jsonify(response)
            except (Exception, psycopg2.DatabaseError) as error:
                response = {"status": StatusCodes["internal_error"], "errors": str(error)}
                return flask.jsonify(response)

            finally:
                if conn is not None:
                    cur.close()
                    conn.close()

            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/")
def landing_page():
    return """
    <!doctype html>
    <html lang=en>
    <head>
        <title>REST API</title>
    </head>
    <body style="background:orange; height: 100%; margin: 0; display: grid; place-items: center">
        <div style="text-align: center">
            <h1>Hey there!</h1>
            <p>Please refer to the documentation for instructions on how to use the endpoints.</p>
        </div>
    </body>
    </html>
    """

@app.route("/dbproj/consumer", methods=["POST"])
def register_consumer():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"username", "password", "email", "birthday"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    # Assign the fields to variables
    username = payload["username"]
    password = payload["password"]
    email = payload["email"]
    birthday = payload["birthday"]

    # Verify that the username meets the requirements
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        response = {"status": StatusCodes["bad_request"], "errors": "Username can only contain letters, numbers and underscores!"}
        return flask.jsonify(response)
    # Verify that the password meets the requirements
    if not re.match(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*\W).{8,}$", password):
        response = {"status": StatusCodes["bad_request"], "errors": "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!"}
        return flask.jsonify(response)
    # Verify that the email is in the correct format
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid email!"}
        return flask.jsonify(response)
    # Verify that the birthday is in the correct format
    try:
        datetime.datetime.strptime(birthday, "%Y-%m-%d")
    except ValueError:
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid birthday format! Expected: YYYY-MM-DD"}
        return flask.jsonify(response)

    # Encrypt password
    salt = app.config["SECRET_KEY"]
    password  = hashlib.sha256((password + salt).encode()).hexdigest()

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                WITH inserted_user AS
                (
                    INSERT INTO users (username, password, email, birthday)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                )
                INSERT INTO consumers (users_id)
                SELECT id FROM inserted_user
                RETURNING users_id
                """
    values = (username, password, email, birthday)

    try:
        cur.execute(statement, values)
        conn.commit()
        user_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Consumer added with ID {user_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"Email or username already in use!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/artist", methods=["POST"])
@requires_token(restrict = "administrators")
def register_artist():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"username", "password", "email", "birthday", "publisher"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    # Assign the fields to variables
    username = payload["username"]
    password = payload["password"]
    email = payload["email"]
    birthday = payload["birthday"]
    publisher = payload["publisher"]
    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    admin_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    # Verify that the username meets the requirements
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        response = {"status": StatusCodes["bad_request"], "errors": "Username can only contain letters, numbers and underscores!"}
        return flask.jsonify(response)
    # Verify that the password meets the requirements
    if not re.match(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*\W).{8,}$", password):
        response = {"status": StatusCodes["bad_request"], "errors": "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!"}
        return flask.jsonify(response)
    # Verify that the email is in the correct format
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid email!"}
        return flask.jsonify(response)
    # Verify that the birthday is in the correct format
    try:
        datetime.datetime.strptime(birthday, "%Y-%m-%d")
    except ValueError:
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid birthday format! Expected: YYYY-MM-DD"}
        return flask.jsonify(response)

    # Encrypt password
    salt = app.config["SECRET_KEY"]
    password  = hashlib.sha256((password + salt).encode()).hexdigest()

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                WITH inserted_user AS
                (
                    INSERT INTO users (username, password, email, birthday)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                )
                INSERT INTO artists (users_id, publishers_id, administrators_users_id)
                SELECT id, %s, %s FROM inserted_user
                RETURNING users_id
                """
    values = (username, password, email, birthday, publisher, admin_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        user_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Artist added with ID {user_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"Email or username already in use!"}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        # Only need to warn about publisher not existing because admin is guaranteed by user token
        response = {"status": StatusCodes["bad_request"], "errors": f"Publisher does not exist!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/user/", methods = ["PUT"])
def authenticate_user():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"username_or_email", "password"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    # Assign the fields to variables
    username_or_email = payload["username_or_email"]
    password = payload["password"]

    # Encrypt password to match the one in the database
    salt = app.config["SECRET_KEY"]
    password  = hashlib.sha256((password + salt).encode()).hexdigest()

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = "SELECT password, id FROM users WHERE username = %s OR email = %s"
    values = (username_or_email, username_or_email)

    try:
        cur.execute(statement, values)
        result = cur.fetchone()
        if result is not None:
            hashed_password = result[0]
            user_id = result[1]
            if hashed_password == password:
                token = jwt.encode({"user_id": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)}, app.config["SECRET_KEY"], algorithm="HS256")
                response = {"status": StatusCodes["success"], "results": str(token)}
            else:
                response = {"status": StatusCodes["bad_request"], "errors": "Wrong password!"}
        else:
            response = {"status": StatusCodes["bad_request"], "errors": "User not found with this username or email!"}
    except (Exception, psycopg2.DatabaseError) as error:
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/songs/", methods=["POST"])
@requires_token(restrict = "artists")
def add_song():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"ismn", "title", "genre", "duration", "release_date", "explicit"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    # Assign the fields to variables
    ismn = payload["ismn"]
    title = payload["title"]
    genre = payload["genre"]
    duration = payload["duration"]
    release_date = payload["release_date"]
    explicit = payload["explicit"].lower()
    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    artist_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    # Verify that the ismn is in the correct format
    if not re.match(r"^[0-9]{13}$", ismn):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid ISMN!"}
        return flask.jsonify(response)
    # Verify that the duration is in the correct format
    if not re.match(r"^\d{1,4}$"):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid duration, must be number of seconds between 0 and 9999!"}
        return flask.jsonify(response)
    # Verify that the release_date is in the correct format
    try:
        datetime.datetime.strptime(release_date, "%Y-%m-%d")
    except ValueError:
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid release date format! Expected: YYYY-MM-DD"}
        return flask.jsonify(response)
    # Verify that the explicit is in the correct format
    if explicit != "true" and explicit != "false":
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid explicit value, must be true or false!"}
        return flask.jsonify(response)

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                INSERT INTO songs (ismn, title, genre, duration, release_date, explicit, artists_users_id)"
                values (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
    values = (ismn, title, genre, duration, release_date, explicit, artist_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        song_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Song added with ID {song_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"Song with this ISMN already added!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/albums/", methods=["POST"])
@requires_token(restrict = "artists")
def add_album():
    # TODO kinda confused on this one
    # é preciso inserir logo uma musica? Ou quando criamos uma musica criamos um album?
    # E como se usa a order?
    logger.info("POST /album/")
    payload = flask.request.get_json()

@app.route("/songs/<keyword>", methods=["GET"])
@requires_token(restrict = "consumers_regular")
def get_song(keyword):

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                    SELECT songs.title, ARRAY_AGG(artists_users_id) AS artists, ARRAY_AGG(albums.id) AS albums
                    FROM songs
                    LEFT JOIN artists_songs ON songs.id = artists_songs.songs_id
                    LEFT JOIN albums ON albums.id = (SELECT album_orders.albums_id FROM album_orders WHERE album_orders.songs_id = songs.id)
                    WHERE songs.title LIKE CONCAT('%', %s, '%')
                    GROUP BY songs.id
                """
    values = (keyword,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"status": StatusCodes["not_found"], "message": "No songs found!"}
        else:
            results = []
            for row in rows:
                title = row[0]
                artists = row[1]
                albums = row[2]
                result = {"title": title, "artists": artists, "albums": albums if albums is not None else []}
                results.append(result)
            response = {"status": StatusCodes["success"], "results": results}
    except (Exception, psycopg2.DatabaseError) as error:
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}


    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/artist_info/<artist_id>", methods=["GET"])
@requires_token(restrict = "consumers_regular")
def get_artist(artist_id):

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                SELECT a.title, s.id AS song_id, al.id AS album_id, p.id AS playlist_id
                FROM artists AS ar
                LEFT JOIN artists_songs AS ars ON ar.users_id = ars.artists_users_id
                LEFT JOIN songs AS s ON ars.songs_id = s.id
                LEFT JOIN albums AS al ON s.artists_users_id = al.artists_users_id
                LEFT JOIN album_orders AS ao ON al.id = ao.albums_id
                LEFT JOIN playlists AS p ON ao.songs_id = p.id
                LEFT JOIN playlist_orders AS po ON s.id = po.songs_id AND p.id = po.playlists_id
                WHERE ar.users_id = %s
                """
    values = (artist_id,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"status": StatusCodes["not_found"],"errors": f"No artist found with this ID {artist_id}!"}
        else:
            artist_id, artist_name, song_ids, album_ids, playlist_ids = rows[0]
            response = {
                "status": StatusCodes["success"],
                "results": {
                    "name": artist_name,
                    "songs": song_ids if song_ids is not None else [],
                    "albums": album_ids if album_ids is not None else [],
                    "playlists": playlist_ids if playlist_ids is not None else []
                }
            }
    except (Exception, psycopg2.DatabaseError) as error:
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/subcription", methods=["POST"])
@requires_token(restrict = "consumers_regular")
def add_subscription():
    return "TODO"

@app.route("/dbproj/playlists", methods=["POST"])
@requires_token(restrict = "consumers_premium")
def add_playlist():
    logger.info("POST /playlist/")
    payload = flask.request.get_json()
    conn = db_connect()
    cur = conn.cursor()

    if "name" not in payload:
        response = {"status": StatusCodes["bad_request"], "results": "ismn value not in payload"}
        return flask.jsonify(response)

    # FIXME list of tracks to add to playlist
    statement = "INSERT INTO playlists (id, name, visibility, consumer_userr)" \
                "values (%d, %s, %s, %s)"
    values = (random.randint(0, 1000), payload["name"], payload["visibility"], payload["consumer_userr"])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {"status": StatusCodes["success"], "results": "Playlist added!"}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"POST /playlist - error: {error}")
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/streams/<ismn>", methods=["PUT"])
@requires_token(restrict = "consumers_regular")
def stream_song(ismn):
    logger.info("POST /stream/")
    payload = flask.request.get_json()

    conn = db_connect()
    cur = conn.cursor()

    logger.debug(f"POST /stream - payload: {payload}")

    if "ismn" not in payload:
        response = {"status": StatusCodes["bad_request"], "results": "ismn value not in payload"}
        return flask.jsonify(response)

    # FIXME isto com ints e assim está a confundir-me um pouco, no meu do ano passado temos tudo como %s
    # TODO acho que as datas assim devem funcionar
    statement = "INSERT INTO streams (ismn, stream_date, consumer_userr)" \
                "values (%d, %s, %s)"
    values = (int(payload["ismn"]), datetime.date.today().isoformat(), payload["consumer_userr"])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {"status": StatusCodes["success"], "results": "Song streamed!"}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"POST /stream - error: {error}")
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/card", methods=["POST"])
@requires_token(restrict = "administrators")
def add_card():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"number", "credit"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    number = payload["number"]
    credit = payload["credit"]
    expiration = datetime.date.today() + datetime.timedelta(days=365)
    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    admin_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    # Verify that the number is in the correct format
    if not re.match(r"^[0-9]{16}$", number):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid card number, must be a 16 digits integer!"}
        return flask.jsonify(response)
    # Verify that the credit is one of the possible options
    if credit != "15" and credit != "25" and credit != "50":
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid credit value, must be 15, 25 or 50!"}
        return flask.jsonify(response)

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                INSERT INTO prepaid_cards (number, credit, expiration, administrators_users_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """
    values = (number, credit, expiration, admin_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        card_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Card added with ID {card_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"Card with this number already in use!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/comments/<song_id>", methods=["POST"])
@requires_token(restrict = "consumers_regular")
def add_comment(song_id):
    # Verify that the song id is in the correct format
    if not re.match(r"^[0-9]{1,18}$", song_id):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid song ID, must be a 1 to 18 digits integer!"}
        return flask.jsonify(response)

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    # Assign the fields to variables
    # Endpoint has no content field in this demo, add dummy text
    content = "Look at my nice comment!"
    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    user_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    statement = """
                INSERT INTO comments (content, post_date, comments_id, songs_id, consumers_users_id)
                VALUES (%s, CURRENT_DATE, %s, %s, %s)
                RETURNING id
                """
    values = (content, None, song_id, user_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        comment_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Comment added with ID {comment_id}!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"No song with ID {song_id} found!"}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/comments/<song_id>/<parent_comment_id>", methods=["POST"])
@requires_token(restrict = "consumers_regular")
def add_comment_reply(song_id, parent_comment_id):
    # Verify that the song id is in the correct format
    if not re.match(r"^[0-9]{1,18}$", song_id):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid song ID, must be a 1 to 18 digits integer!"}
        return flask.jsonify(response)
    # Verify that the parent comment id is in the correct format
    if not re.match(r"^[0-9]{1,18}$", parent_comment_id):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid parent comment ID, must be a 1 to 18 digits integer!"}
        return flask.jsonify(response)

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    # Assign the fields to variables
    # Endpoint has no content field in this demo, add dummy text
    content = "Look at my nice comment!"
    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    user_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    statement = """
                INSERT INTO comments (content, post_date, comments_id, songs_id, consumers_users_id)
                VALUES (%s, CURRENT_DATE, %s, %s, %s)
                RETURNING id
                """
    values = (content, parent_comment_id, song_id, user_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        comment_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Comment added with ID {comment_id}!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"No song with ID {song_id} or comment with ID {parent_comment_id} found!"}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

@app.route("/dbproj/report/topN/<year_month>", methods=["GET"])
@requires_token(restrict = "consumers_regular")
def get_report(year_month):
    # Verify that the year_month is in the correct format
    try:
        year_month = datetime.datetime.strptime(year_month, "%Y-%m")
    except ValueError:
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid release date format! Expected: YYYY-MM"}
        return flask.jsonify(response)

    # Subtract 12 months from the date
    year_month = year_month - datetime.timedelta(days=365)

    # No need to validate token since it is already done by the decorator
    token = flask.request.headers.get("JWT-Token")
    consumer_id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                SELECT
                    EXTRACT(YEAR_MONTH FROM songs.release_date) AS month,
                    songs.genre,
                    COUNT(*) AS playbacks
                FROM
                    streams
                JOIN
                    songs ON streams.songs_id = songs.id
                WHERE
                    streams.consumers_users_id = %s
                    AND streams.stream_date >= %s
                GROUP BY
                    month,
                    songs.genre
                ORDER BY
                    month DESC,
                    playbacks DESC;
                """
    values = (consumer_id, year_month)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        results = []
        for row in rows:
            month = row[0]
            genre = row[1]
            playbacks = row[2]
            result = {"month": month, "genre": genre, "playbacks": playbacks}
            results.append(result)
        if results == []:
            response = {"status": StatusCodes["success"], "results": "No stream history!"}
        else:
            response = {"status": StatusCodes["success"], "results": results}
    except (Exception, psycopg2.DatabaseError) as error:
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

# Extra endpoints
@app.route("/dbproj/publishers", methods=["POST"])
@requires_token(restrict = "administrators")
def add_publisher():
    payload = flask.request.get_json()

    # Verify that the number of fields is correct
    required = {"name", "email"}
    received = set(payload.keys())
    difference = list(required.difference(received))
    if len(difference) > 0:
        response = {"status": StatusCodes["bad_request"], "errors": f"Missing or unexpected fields: {difference}"}
        return flask.jsonify(response)

    # Assign the fields to variables
    name = payload["name"]
    email = payload["email"]

    # Verify that the email is in the correct format
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        response = {"status": StatusCodes["bad_request"], "errors": "Invalid email!"}
        return flask.jsonify(response)

    conn = db_connect()
    if conn is None:
        response = {"status": StatusCodes["internal_error"], "errors": "Could not connect to the database!"}
        return flask.jsonify(response)
    cur = conn.cursor()

    statement = """
                INSERT INTO publishers (name, email)
                VALUES (%s, %s)
                RETURNING id
                """
    values = (name, email)

    try:
        cur.execute(statement, values)
        conn.commit()
        publisher_id = cur.fetchone()[0]
        response = {"status": StatusCodes["success"], "results": f"Publisher added with ID {publisher_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        response = {"status": StatusCodes["bad_request"], "errors": f"Email already in use!"}
    except (Exception, psycopg2.DatabaseError) as error:
        conn.rollback()
        response = {"status": StatusCodes["internal_error"], "errors": str(error)}

    finally:
        if conn is not None:
            cur.close()
            conn.close()

    return flask.jsonify(response)

if __name__ == "__main__":
    # Setup logging
    try:
        os.makedirs("logs")
    except FileExistsError:
        pass
    log = "logs/" + datetime.date.today().isoformat() + ".log"
    logger = logging.getLogger("logger")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    file_handler = logging.FileHandler(log)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info("Intializing REST API")

    # Define status codes
    StatusCodes = {
    "success": 200,
    "bad_request": 400,
    "internal_error": 500
    }

    logger.info("Defined status codes")

    # Load environment variables
    dotenv.load_dotenv()

    logger.info("Loaded environment variables")

    # Setup server
    app.config["SECRET_KEY"] = os.environ.get("SERVER_SECRET_KEY")
    host = os.environ.get("SERVER_HOST")
    port = os.environ.get("SERVER_PORT")
    logger.info(f"REST API online")
    app.run(host = host, threaded = True, port = port)
