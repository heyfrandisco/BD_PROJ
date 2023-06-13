import flask
import flask_limiter
import psycopg2
import datetime
import hashlib
import secrets
import jwt
import dotenv
import os
import functools
import utils
import werkzeug # werkzeug.exceptions.HTTPException is raised when flask.abort() is called

# Define app name
app = flask.Flask(__name__)
# Create rate limiter
limiter = flask_limiter.Limiter(flask_limiter.util.get_remote_address, app = app, default_limits = ["500/hour","3/second"])

def requires_authentication(restrict = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            auth = flask.request.headers.get("Authorization")

            # Check if the "Authorization" header exists and starts with "Bearer" as sent by the postman collection
            if not auth or not auth.startswith("Bearer "):
                flask.abort(utils.StatusCodes["unauthorized"], "You must be authenticated to perform this action!")
            try:
                # Get the token after the "Bearer " part
                token = auth.split(" ")[1]
                token_info = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                flask.abort(utils.StatusCodes["unauthorized"], "Your session has expired, please authenticate again!")
            except jwt.InvalidTokenError:
                flask.abort(utils.StatusCodes["unauthorized"], "Your session is invalid, please authenticate again!")

            user_id = token_info["user_id"]

            try:
                conn, cur = utils.db_connect()

                statement = """
                            SELECT CASE
                                WHEN EXISTS (SELECT 1 FROM bans WHERE bans.users_id = users.id
                                    AND (bans.end_time IS NULL or bans.end_time > CURRENT_TIMESTAMP)) THEN 'banned'
                                WHEN EXISTS (SELECT 1 FROM consumers WHERE consumers.users_id = users.id)
                                    AND EXISTS (SELECT 1 FROM subscriptions WHERE subscriptions.consumers_users_id = users.id
                                        AND subscriptions.end_time + INTERVAL '1 minute' > CURRENT_TIMESTAMP) THEN 'premium consumer'
                                WHEN EXISTS (SELECT 1 FROM consumers WHERE consumers.users_id = users.id) THEN 'consumer'
                                WHEN EXISTS (SELECT 1 FROM artists WHERE artists.users_id = users.id) THEN 'artist'
                                WHEN EXISTS (SELECT 1 FROM administrators WHERE administrators.users_id = users.id) THEN 'administrator'
                            END AS user_role
                            FROM users
                            WHERE id = %s;
                            """
                values = (user_id,)
                cur.execute(statement, values)

                user_role = cur.fetchone()[0]
                if not user_role:
                    raise Exception
                if user_role == "banned":
                    flask.abort(utils.StatusCodes["forbidden"], "You are banned, contact support for more details!")

            except werkzeug.exceptions.HTTPException:
                raise
            except Exception:
                flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
            finally:
                utils.db_disconnect(conn, cur)

            # If no restrict list is passed as argument, just check if the token is valid
            if restrict:
                if not utils.list_validate(restrict) or not (utils.string_validate(role) for role in restrict):
                    flask.abort(utils.StatusCodes["internal_error"], "Invalid restrict list in this endpoint!")
                for role in restrict:
                    # If the user role is in the restrict list, allow entry to the endpoint (premium consumers can access regular consumer endpoints)
                    if user_role == role or (user_role == "premium consumer" and role == "consumer"):
                        return func(user_id, user_role, *args, **kwargs)
                flask.abort(utils.StatusCodes["unauthorized"], "You do not have permission to perform this action!")

            return func(user_id, user_role, *args, **kwargs)
        return wrapper
    return decorator

@app.route("/")
@limiter.exempt
def landing_page():
    response = {"results": "Welcome to our API, please refer to the documentation for information on how to use the endpoints!"}
    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

# Serve favicon to clients that request it (e.g. browsers)
@app.route("/favicon.ico", methods=["GET"])
@limiter.exempt
def favicon():
    return flask.send_from_directory(os.path.join(app.root_path, "res"), "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/dbproj/consumer", methods=["POST"])
# Prevent spam account creation with stricter rate limiting
@limiter.limit("2/second")
@limiter.limit("5/minute")
@limiter.limit("10/hour")
@limiter.limit("15/day")
def register_consumer():
    payload = flask.request.get_json()

    required = {"username", "password", "email", "birthday","display_name"}
    utils.payload_validate(payload, required)

    username = payload["username"]
    password = payload["password"]
    email = payload["email"]
    birthday = payload["birthday"]
    display_name = payload["display_name"]

    # Verify fields
    if not utils.string_validate(username, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid username! Expected string with length: 1 to 512")
    if not utils.string_validate(password, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid password! Expected string with length: 1 to 512")
    if not utils.string_validate(email, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email! Expected string with length: 1 to 512")
    if not utils.string_validate(display_name, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid display name! Expected string with length: 1 to 512")
    if not utils.datetime_validate(birthday, "%Y-%m-%d", past = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid birthday! Expected past date string in ISO 8601 format: YYYY-MM-DD")

    # Verify that the password meets the requirements
    if not utils.password_validate(password):
        flask.abort(utils.StatusCodes["bad_request"],
        "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!")
    # Verify that the email is in the correct format
    if not utils.email_validate(email):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email!")

    # Encrypt password
    password_salt = secrets.token_hex(16)
    password_pepper = app.config["SECRET_KEY"]
    password_hash  = hashlib.sha512((password + password_salt + password_pepper).encode("utf-8")).hexdigest()

    conn, cur = utils.db_connect()

    statement = """
                WITH inserted_user AS
                (
                    INSERT INTO users (username, password_hash, password_salt, email)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                )
                INSERT INTO consumers (users_id, birthday, display_name, register_date)
                SELECT inserted_user.id, %s, %s, CURRENT_DATE
                FROM inserted_user
                RETURNING users_id
                """
    values = (username, password_hash, password_salt, email, birthday, display_name)

    try:
        cur.execute(statement, values)
        conn.commit()
        user_id = cur.fetchone()[0]
        response = {"results": f"Consumer added with ID {user_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "Username or email already in use!")
    except psycopg2.DatabaseError as e:
        print(e)
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/artist", methods=["POST"])
@requires_authentication(restrict = ["administrator"])
def register_artist(user_id, user_role):
    payload = flask.request.get_json()

    required = {"username", "password", "email", "stage_name", "publisher"}
    utils.payload_validate(payload, required)

    username = payload["username"]
    password = payload["password"]
    email = payload["email"]
    stage_name = payload["stage_name"]
    publisher = payload["publisher"]
    admin_id = user_id

    # Verify fields
    if not utils.string_validate(username, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid username! Expected string with length: 1 to 512")
    if not utils.string_validate(password, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid password! Expected string with length: 1 to 512")
    if not utils.string_validate(email, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email! Expected string with length: 1 to 512")
    if not utils.string_validate(stage_name, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid stage name! Expected string with length: 1 to 512")
    if not utils.integer_validate(publisher, min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid publisher! Expected integer with value: 1 to 9223372036854775807")

    # Verify that the password meets the requirements
    if not utils.password_validate(password):
        flask.abort(utils.StatusCodes["bad_request"],
        "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character!")
    # Verify that the email is in the correct format
    if not utils.email_validate(email):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email!")

    # Encrypt password
    password_salt = secrets.token_hex(16)
    password_pepper = app.config["SECRET_KEY"]
    password_hash  = hashlib.sha512((password + password_salt + password_pepper).encode("utf-8")).hexdigest()

    conn, cur = utils.db_connect()

    statement = """
                WITH inserted_user AS
                (
                    INSERT INTO users (username, password_hash, password_salt, email)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                )
                INSERT INTO artists (users_id, stage_name, publishers_id, administrators_users_id)
                SELECT id, %s, %s, %s
                FROM inserted_user
                RETURNING users_id
                """
    values = (username, password_hash, password_salt, email, stage_name, publisher, admin_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        user_id = cur.fetchone()[0]
        response = {"results": f"Artist added with ID {user_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "Email or username already in use!")
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], f"No publisher found with ID {publisher}!")
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/user", methods = ["PUT"])
# Prevent brute force attacks on passwords with stricter rate limiting
@limiter.limit("2/second")
@limiter.limit("10/minute")
@limiter.limit("20/hour")
@limiter.limit("30/day")
def authenticate_user():
    payload = flask.request.get_json()

    required = {"username_or_email", "password"}
    utils.payload_validate(payload, required)

    username_or_email = payload["username_or_email"]
    password = payload["password"]

    # Verify fields
    if not utils.string_validate(username_or_email, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid username or email! Expected string with length: 1 to 512")
    if not utils.string_validate(password, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid password! Expected string with length: 1 to 512")

    # Verify that the password meets the requirements so we can return wrong password without having to run the query if it doesn't meet them
    if not utils.password_validate(password):
        flask.abort(utils.StatusCodes["unauthorized"], "Wrong password!")

    try:
        conn, cur = utils.db_connect()

        statement = """
                    SELECT password_hash, password_salt, id,
                        CASE
                            WHEN EXISTS (SELECT 1 FROM bans WHERE bans.users_id = users.id
                                AND (bans.end_time IS NULL or bans.end_time > CURRENT_TIMESTAMP)) THEN true
                        END AS banned
                    FROM users
                    WHERE username = %s OR email = %s
                    """
        values = (username_or_email, username_or_email)
        cur.execute(statement, values)

        user_data = cur.fetchone()
        if user_data:
            stored_password_hash = user_data[0]
            stored_passwrod_salt = user_data[1]
            user_id = user_data[2]
            banned = user_data[3]
            if banned:
                flask.abort(utils.StatusCodes["forbidden"], "You are banned, contact support for more details!")
            # Encrypt password to match the one in the database
            password_pepper = app.config["SECRET_KEY"]
            password_hash  = hashlib.sha512((password + stored_passwrod_salt + password_pepper).encode("utf-8")).hexdigest()
            if password_hash == stored_password_hash:
                token = jwt.encode({
                                    "user_id": user_id,
                                    "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
                                    }, app.config["SECRET_KEY"], algorithm="HS256")
                response = {"results": str(token)}
            else:
                flask.abort(utils.StatusCodes["unauthorized"], "Wrong password!")
        else:
            flask.abort(utils.StatusCodes["unauthorized"], f"No user found with username or email {username_or_email}!")

        # Can implement a notification system here to notify the user that there was a login for any first time ip
        statement = """
                    INSERT INTO logins (users_id, login_time, ip)
                    VALUES (%s, CURRENT_TIMESTAMP, %s)
                    RETURNING id
                    """
        values = (user_id, utils.get_request_ip())
        cur.execute(statement, values)

        login_id = cur.fetchone()[0]
        if not login_id:
            raise Exception

        conn.commit()

    except werkzeug.exceptions.HTTPException:
        raise
    except Exception:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/song", methods=["POST"])
@requires_authentication(restrict = ["artist"])
def add_song(user_id, user_role):
    payload = flask.request.get_json()
    artist_id = user_id

    required = {"ismn", "title", "genre", "duration", "release_date", "explicit", "collaborator_list"}
    utils.payload_validate(payload, required)

    ismn = payload["ismn"]
    title = payload["title"]
    genre = payload["genre"]
    duration = payload["duration"]
    release_date = payload["release_date"]
    explicit = payload["explicit"]
    collaborator_list = payload["collaborator_list"]

    # Verify fields
    if not utils.string_validate(ismn, min_len = 13, max_len = 13, only_digits = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid ISMN! Expected string of digits with length: 13")
    if not utils.string_validate(title, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid title! Expected string with length: 1 to 512")
    if not utils.string_validate(genre, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid genre! Expected string with length: 1 to 512")
    if not utils.integer_validate(duration, min_val = 1, max_val = 3600):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid duration! Expected integer with value: 1 to 3600")
    if not utils.datetime_validate(release_date, "%Y-%m-%d", past = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid release date! Expected past date string in ISO 8601 format: YYYY-MM-DD")
    if not utils.boolean_validate(explicit):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid explicit value! Expected boolean with value: true or false!")
    if not utils.list_validate(collaborator_list, max_len = 10):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid collaborator list! Expected array of integers with length: 0 to 10")
    for collaborator_id in collaborator_list:
        if not utils.integer_validate(collaborator_id, min_val = 1, max_val = 9223372036854775807):
            flask.abort(utils.StatusCodes["bad_request"], "Invalid collaborator ID in list! Expected integers with values: 1 to 9223372036854775807")
        if collaborator_id == artist_id:
            flask.abort(utils.StatusCodes["bad_request"], "Cannot add yourself as a collaborator!")

    conn, cur = utils.db_connect()

    statement = """
                WITH inserted_song AS
                (
                    INSERT INTO songs (ismn, title, genre, duration, release_date, explicit, artists_users_id, publishers_id)
                    SELECT %s, %s, %s, %s, %s, %s, %s, publishers_id
                    FROM artists WHERE users_id = %s
                    RETURNING id
                ),
                inserted_collab AS
                (
                    INSERT INTO collaborations (artists_users_id, songs_id)
                    SELECT collaborator_id, inserted_song.id
                    FROM inserted_song, UNNEST(%s::int[]) AS collaborator_id
                )
                SELECT id FROM inserted_song;
                """
    values = (ismn, title, genre, duration, release_date, explicit, artist_id, artist_id, collaborator_list)

    try:
        cur.execute(statement, values)
        conn.commit()
        song_id = cur.fetchone()[0]
        response = {"results": f"Song added with ID {song_id}!"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "Song with this ISMN already added or you already have a song with this exact title!")
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "No artist found with one of the IDs in the collaborator list!")
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/album", methods=["POST"])
@requires_authentication(restrict = ["artist"])
def add_album(user_id, user_role):
    payload = flask.request.get_json()
    artist_id = user_id

    required = {"title", "release_date", "existing_song_list", "new_song_list"}
    utils.payload_validate(payload, required)

    title = payload["title"]
    release_date = payload["release_date"]
    new_song_list = payload["new_song_list"]
    existing_song_list = payload["existing_song_list"]

    # Verify fields
    if not utils.string_validate(title, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid title! Expected string with length: 1 to 512")
    if not utils.datetime_validate(release_date, "%Y-%m-%d", past = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid release date! Expected past date string in ISO 8601 format: YYYY-MM-DD")
    if not len(new_song_list) + len(existing_song_list) in range(2, 10001):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid length for song lists! Expected combined length in range: 2 to 10000")
    if not utils.list_validate(existing_song_list, min_len = 0, max_len = 10000):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid existing song list! Expected list in format [1, 2, ...] with length: 0 to 10000")
    for song_id in existing_song_list:
        if not utils.integer_validate(song_id, min_val = 1, max_val = 9223372036854775807):
            flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID in the song list! Expected integer in range: 1 to 9223372036854775807")
    if not utils.list_validate(new_song_list, min_len = 0, max_len = 10000):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid new song list! Expected list in format [1, 2, ...] with length: 0 to 10000")
    for song in new_song_list:
        song = song.strip()
        pass #TODO


    try:
        conn, cur = utils.db_connect()

        # Use ordinality to preserve the song order given by the user in the array
        statement = """
                    WITH inserted_album AS
                    (
                        INSERT INTO albums (title, release_date, artists_users_id)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    ),
                    inserted_album_song AS
                    (
                        INSERT INTO albums_songs (albums_id, songs_id, ordinality)
                        SELECT songs.ordinality, songs.id, inserted_album.id
                        FROM inserted_album, UNNEST(%s::int[]) WITH ORDINALITY AS songs(id, ordinality)
                    )
                    SELECT id FROM inserted_album;
                    """
        values = (title, release_date, artist_id, existing_song_list)
        cur.execute(statement, values)

        album_id = cur.fetchone()[0]
        if not album_id:
            raise psycopg2.DatabaseError

        conn.commit()
        response = {"results": f"Album added with ID {album_id}!"}

    except werkzeug.exceptions.HTTPException:
        raise
    except psycopg2.errors.ForeignKeyViolation:
        flask.abort(utils.StatusCodes["bad_request"], "No song was found with one of the IDs in the song list!")
    except psycopg2.errors.UniqueViolation:
        flask.abort(utils.StatusCodes["bad_request"], "You already have an album with this exact title!")
    except Exception:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/playlist", methods=["POST"])
@requires_authentication(restrict = ["premium consumer"])
def add_playlist(user_id, user_role):
    payload = flask.request.get_json()
    consumer_id = user_id

    required = {"name", "private", "song_list"}
    utils.payload_validate(payload, required)

    # Assign payload fields to variables
    name = payload["name"]
    private = payload["private"]
    song_list = payload["song_list"]

    # Verify fields
    if not utils.string_validate(name, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid name! Expected string with length: 1 to 512")
    if not utils.boolean_validate(private):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid private value! Expected boolean with value: true or false")
    if not utils.list_validate(song_list, min_len = 1, max_len = 10000):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song list! Expected list in format [1, 2, ...] with length: 1 to 10000")
    for song_id in song_list:
        if not utils.integer_validate(song_id, min_val = 1, max_val = 9223372036854775807):
            flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID in the song list! Expected integer in range: 1 to 9223372036854775807")

    conn, cur = utils.db_connect()

    # Use ordinality to preserve the song order given by the user in the array
    statement = """
                WITH inserted_playlist AS
                (
                    INSERT INTO playlists (name, private, consumers_users_id)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ),
                inserted_playlist_song AS
                (
                    INSERT INTO playlist_orders (position, songs_id, playlists_id)
                    SELECT songs.ordinality, songs.id, inserted_playlist.id
                    FROM inserted_playlist, UNNEST(%s::int[]) WITH ORDINALITY AS songs(id, ordinality)
                )
                SELECT id FROM inserted_playlist;
                """
    values = (name, private, consumer_id, song_list)

    try:
        cur.execute(statement, values)
        conn.commit()
        playlist_id = cur.fetchone()[0]
        response = {"results": f"Playlist added with ID {playlist_id}!"}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "No song was found with one of the IDs in the song list!")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], "You already have a playlist with this exact name!")
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/subscription", methods=["POST"])
@requires_authentication(restrict = ["consumer"])
def add_subscription(user_id, user_role):
    payload = flask.request.get_json()

    required = {"period", "cards"}
    utils.payload_validate(payload, required)

    period = payload["period"]
    cards = payload["cards"]
    consumer_id = user_id

    if not utils.string_validate(period, max_len = 512) or period not in ["month", "quarter", "semester"]:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid period! Expected strings: month, quarter or semester")
    if not utils.list_validate(cards, min_len = 1, max_len = 10000):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid card list! Expected list in format [1, 2, ...] with length: 1 to 10000")
    for card_number in cards:
        if not utils.string_validate(card_number, min_len = 16, max_len = 16):
            flask.abort(utils.StatusCodes["bad_request"], "Invalid card number in the card list! Expected string with length: 16")

    if period == "month":
        price = 7
        interval = "1 month"
    elif period == "quarter":
        price = 21
        interval = "3 months"
    elif period == "semester":
        price = 42
        interval = "6 months"
    remaining_price = price

    try:
        conn, cur = utils.db_connect()

        if user_role == "consumer":
            statement = """
                        INSERT INTO subscriptions (start_time, end_time, price, consumers_users_id)
                        VALUES (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL %s, %s, %s)
                        RETURNING id
                        """
            values = (interval, price, consumer_id)
        elif user_role == "premium consumer":
            # Get end of current subscription
            statement = """
                        SELECT end_time
                        FROM subscriptions
                        WHERE consumers_users_id = %s
                        AND end_time = (SELECT MAX(end_time) FROM subscriptions WHERE consumers_users_id = %s AND end_time > CURRENT_TIMESTAMP)
                        """
            values = (consumer_id,consumer_id)

            cur.execute(statement, values)
            previous_end_time = cur.fetchone()[0]
            if not previous_end_time:
                raise Exception

            statement = """
                        INSERT INTO subscriptions (start_time, end_time, price, consumers_users_id)
                        VALUES (%s, %s + INTERVAL %s, %s, %s)
                        RETURNING id
                        """
            values = (previous_end_time, previous_end_time, interval, price, consumer_id)

        cur.execute(statement, values)
        subscription_id = cur.fetchone()[0]
        if not subscription_id:
            raise psycopg2.DatabaseError

        statement = """
                    SELECT id, number, credit FROM prepaid_cards
                    WHERE number = ANY (ARRAY[%s]::text[])
                    FOR UPDATE
                    """
        values = (cards,)

        cur.execute(statement, values)
        rows = cur.fetchall()
        if len(rows) != len(cards):
            raise psycopg2.errors.ForeignKeyViolation

        for row in rows:
            card_id = row[0]
            card_number = row[1]
            credit = row[2]
            amount_used = min(credit, remaining_price)
            remaining_price -= amount_used

            statement = """
                        INSERT INTO card_payments (amount_used, payment_time, prepaid_cards_id, subscriptions_id)
                        VALUES (%s, CURRENT_TIMESTAMP, %s, %s)
                        """
            values = (amount_used, card_id, subscription_id)

            cur.execute(statement, values)

            statement = "UPDATE prepaid_cards SET credit = credit - %s WHERE number = %s"
            values = (amount_used, card_number)

            cur.execute(statement, values)

        if remaining_price > 0:
            flask.abort(utils.StatusCodes["bad_request"],
            f"Missing {remaining_price:.2f} in the prepaid cards provided to pay {price:.2f} for {period} subscription!")

        conn.commit()
        if user_role == "premium consumer":
            response = {"results": f"Subscription added to the end of your existing subscription with ID {subscription_id}!"}
        else:
            response = {"results": f"Subscription added with ID {subscription_id}!"}

    except werkzeug.exceptions.HTTPException:
        raise
    except psycopg2.errors.ForeignKeyViolation:
        flask.abort(utils.StatusCodes["bad_request"], "No card was found with one of the numbers in the card list or there is a duplicate entry!")
    except Exception as e:
        print(e)
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/song/<keyword>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_song(user_id, user_role, keyword):
    keyword = keyword.replace("+", " ")
    keyword = f"%{keyword}%"

    conn, cur = utils.db_connect()

    statement = """
                SELECT songs.id, songs.title, artists.stage_name
                FROM songs
                LEFT JOIN artists ON artists.users_id = songs.artists_users_id
                WHERE songs.title ILIKE %s
                """
    values = (keyword,)

    keyword = keyword.replace("%", "")

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No songs found with keyword {keyword}!"}
        else:
            results = []
            for row in rows:
                results.append({"id": row[0], "title": row[1], "artist": row[2]})
            response = {"results": results}
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/song_info/<song_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_song_info(user_id, user_role, song_id):
    if not utils.integer_validate(utils.string_to_int(song_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID! Expected integer in range: 1 to 9223372036854775807")

    conn, cur = utils.db_connect()

    statement = """
                SELECT songs.title, artists.stage_name, songs.genre, songs.duration,
                songs.explicit, songs.release_date, collaborators.stage_name, albums.title
                FROM songs
                LEFT JOIN artists ON songs.artists_users_id = artists.users_id
                LEFT JOIN album_orders ON album_orders.songs_id = songs.id
                LEFT JOIN albums ON album_orders.albums_id = albums.id
                LEFT JOIN collaborations ON songs.id = collaborations.songs_id
                LEFT JOIN artists AS collaborators ON collaborations.artists_users_id = collaborators.users_id
                WHERE songs.id = %s
                GROUP BY songs.id, artists.stage_name, collaborators.stage_name, albums.title
                """
    values = (song_id,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No song found with ID {song_id}!"}
        else:
            title, artist_name, genre, duration, explicit, release_date = rows[0][:6]
            minutes = duration // 60
            seconds = duration % 60
            duration = f"{minutes}:{seconds}"
            release_date = release_date.strftime("%Y-%m-%d")
            collab_names = []
            album_names = []
            for row in rows:
                if row[6]:
                    collab_names.append(row[6])
                if row[7]:
                    album_names.append(row[7])
            response = {"results":
                            {
                                "title": title,
                                "artist": artist_name,
                                "collaborators": collab_names if collab_names else ["This song was made with no collaborations!"],
                                "albums": album_names if album_names else ["This song is a single!"],
                                "genre": genre,
                                "duration": duration,
                                "explicit": explicit,
                                "release_date": release_date,
                            }
                        }
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/artist_info/<artist_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_artist_info(user_id, user_role, artist_id):
    if not utils.integer_validate(utils.string_to_int(artist_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid artist ID! Expected integer in range: 1 to 9223372036854775807")

    conn, cur = utils.db_connect()

    statement = """
                SELECT DISTINCT artists.stage_name, songs.title, collabs.title, albums.title, playlists.name, playlists_author.display_name
                FROM artists
                JOIN users ON artists.users_id = users.id
                LEFT JOIN collaborations ON artists.users_id = collaborations.artists_users_id
                LEFT JOIN songs AS collabs ON collaborations.songs_id = collabs.id
                LEFT JOIN songs ON artists.users_id = songs.artists_users_id
                LEFT JOIN albums ON albums.artists_users_id = artists.users_id
                LEFT JOIN playlist_orders ON songs.id = playlist_orders.songs_id
                LEFT JOIN playlists ON playlist_orders.playlists_id = playlists.id AND playlists.private = FALSE
                LEFT JOIN consumers AS playlists_author ON playlists.consumers_users_id = playlists_author.users_id
                WHERE artists.users_id = %s
                """
    values = (artist_id,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No artist found with ID {artist_id}!"}
        else:
            stage_name = rows[0][0]
            songs = []
            collabs = []
            albums = []
            playlists = []
            for row in rows:
                if row[1] and row[1] not in songs:
                    songs.append(row[1])
                if row[2]:
                    collabs.append(row[2])
                if row[3]:
                    albums.append(row[3])
                if row[4] and row[5]:
                    playlist = {"name": row[4], "author": row[5]}
                    if playlist not in playlists:
                        playlists.append(playlist)
            response = {"results":
                            {
                                "stage_name": stage_name,
                                "released_songs": songs if songs else ["This artist has not released any songs!"],
                                "featured_songs": collabs if collabs else ["This artist has not been featured in any songs from other artists!"],
                                "albums": albums if albums else ["This artist has not released any albums!"],
                                "is_in_playlists": playlists if playlists else ["This artist's songs have not been added to any public playlists!"]
                            }
                        }
    except psycopg2.DatabaseError as e:
        print(e)
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/<song_id>", methods=["PUT"])
@requires_authentication(restrict = ["consumer"])
def stream_song(user_id, user_role, song_id):
    # Verify that the song id is valid
    try:
        song_id = int(song_id)
        if song_id < 1 or song_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID!")

    consumer_id = user_id

    conn, cur = utils.db_connect()

    statement = """
                INSERT INTO streams (songs_id, consumers_users_id, stream_time)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                RETURNING id
                """
    values = (song_id, consumer_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        stream_id = cur.fetchone()[0]
        response = {"results": f"Song streamed and stored in history with ID {stream_id}!"}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], f"No song with ID {song_id} found!")
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response)), utils.StatusCodes["success"]

@app.route("/dbproj/card", methods=["POST"])
@requires_authentication(restrict = ["administrator"])
def add_prepaid_card(user_id, user_role):
    payload = flask.request.get_json()

    required = {"number", "credit"}
    utils.payload_validate(payload, required)

    number = payload["number"]
    credit = payload["credit"]
    expiration = "1 year"
    admin_id = user_id

    if not utils.string_validate(number, min_len = 16, max_len = 16, only_digits = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid card number! Expected string of digits with length: 16")
    if not utils.integer_validate(credit) and credit != "15" and credit != "25" and credit != "50":
        flask.abort(utils.StatusCodes["bad_request"], "Invalid credit! Expected integer with value: 15, 25, or 50")

    try:
        conn, cur = utils.db_connect()

        statement = """
                    INSERT INTO prepaid_cards (number, credit, expiration, administrators_users_id)
                    VALUES (%s, %s, CURRENT_DATE + INTERVAL %s, %s)
                    RETURNING id
                    """
        values = (number, credit, expiration, admin_id)

        cur.execute(statement, values)
        card_id = cur.fetchone()[0]

        conn.commit()
        response = {"results": f"Card added with ID {card_id}!"}

    except psycopg2.errors.UniqueViolation:
        flask.abort(utils.StatusCodes["bad_request"], f"Card with this number already exists!")
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    except werkzeug.exceptions.HTTPException:
        conn.rollback()
        utils.db_disconnect(conn, cur)
        raise

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/comment/<song_id>", methods=["POST"])
@requires_authentication(restrict = ["consumer"])
def add_comment(user_id, user_role, song_id):
    # Verify that the song id is in the correct format
    try:
        song_id = int(song_id)
        if song_id < 1 or song_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID!")

    conn, cur = utils.db_connect()

    consumer_id = user_id
    # Endpoint has no content field in this demo, add dummy text
    content = "Look at my nice comment!"

    statement = """
                INSERT INTO comments (content, post_time, comments_id, songs_id, consumers_users_id)
                VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING id
                """
    values = (content, None, song_id, consumer_id)

    try:
        cur.execute(statement, values)
        conn.commit()
        comment_id = cur.fetchone()[0]
        response = {"results": f"Comment added with ID {comment_id}!"}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], f"No song with ID {song_id} found!")
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/comment/<song_id>/<parent_comment_id>", methods=["POST"])
@requires_authentication(restrict = ["consumer"])
def add_comment_reply(user_id, user_role, song_id, parent_comment_id):
    # Verify that the song id is in the correct format
    try:
        song_id = int(song_id)
        if song_id < 1 or song_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID!")
    # Verify that the parent comment id is in the correct format
    try:
        parent_comment_id = int(parent_comment_id)
        if parent_comment_id < 1 or parent_comment_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid parent comment ID!")

    conn, cur = utils.db_connect()

    # Endpoint has no content field in this demo, add dummy text
    content = f"Look at my nice reply to number {parent_comment_id}!"
    consumer_id = user_id

    statement = """
                INSERT INTO comments (content, post_time, comments_id, songs_id, consumers_users_id)
                VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING id
                """
    values = (content, parent_comment_id, song_id, consumer_id)

    try:
        cur.execute(statement, values)
        comment_id = cur.fetchone()[0]
        # Check if user is replying to the newly generated ID for this very same reply by the DBMS (prevent infinite recursion)
        if int(comment_id) == parent_comment_id:
            raise psycopg2.errors.ForeignKeyViolation
        conn.commit()
        response = {"results": f"Comment added with ID {comment_id}!"}
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flask.abort(utils.StatusCodes["bad_request"], f"No parent comment with ID {parent_comment_id} found for song with ID {song_id}!")
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/report/<year_month>", methods=["GET"])
@requires_authentication(restrict = ["consumer"])
def get_report(user_id, user_role, year_month):
    if not utils.datetime_validate(year_month, "%Y-%m", past = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid year and month combination! Expected past date in format: YYYY-MM")

    year_month = datetime.datetime.strptime(year_month, "%Y-%m")

    # Subtract 12 months from the date
    start_date = year_month - datetime.timedelta(days=365)
    # Conver to timestamp
    start_date = year_month.timestamp()
    start_date = datetime.datetime.fromtimestamp(start_date)

    consumer_id = user_id

    conn, cur = utils.db_connect()

    statement = """
                SELECT EXTRACT(YEAR FROM streams.stream_time) AS year,
                       EXTRACT(MONTH FROM streams.stream_time) AS month, songs.genre, COUNT(*) AS playbacks
                FROM streams
                JOIN songs ON streams.songs_id = songs.id
                WHERE streams.consumers_users_id = %s AND streams.stream_time >= %s
                GROUP BY year, month, songs.genre
                ORDER BY year DESC, month DESC, playbacks DESC;
                """
    values = (consumer_id, start_date)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No stream history found for the 12 months before {year_month.strftime('%Y-%m')}!"}
        else:
            results = []
            for row in rows:
                year, month, genre, playbacks = row
                results.append({"year_month": f"{year}-{month}", "genre": genre, "playbacks": playbacks})
            response = {"results": results}
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

# All endpoints under here are extra (not required for project)

@app.route("/dbproj/publisher", methods=["POST"])
@requires_authentication(restrict = ["administrator"])
def add_publisher(user_id, user_role):
    payload = flask.request.get_json()

    required = {"name", "email"}
    utils.payload_validate(payload, required)

    name = payload["name"]
    email = payload["email"]

    if not utils.string_validate(name, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid name! Expected string with length: 1 to 512")
    if not utils.string_validate(email, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email! Expected string with length: 1 to 512")
    if not utils.email_validate(email):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid email!")

    try:
        conn, cur = utils.db_connect()

        statement = """
                    INSERT INTO publishers (name, email)
                    VALUES (%s, %s)
                    RETURNING id
                    """
        values = (name, email)

        cur.execute(statement, values)
        conn.commit()
        publisher_id = cur.fetchone()[0]
        response = {"results": f"Publisher added with ID {publisher_id}!"}

    except psycopg2.errors.UniqueViolation:
        flask.abort(utils.StatusCodes["bad_request"], "Email already in use!")
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    except werkzeug.exceptions.HTTPException:
        conn.rollback()
        utils.db_disconnect(conn, cur)
        raise

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/playlist/<playlist_id>", methods=["DELETE"])
@requires_authentication(restrict = ["consumer"])
def delete_playlist(user_id, user_role, playlist_id):
    if not utils.integer_validate(utils.string_to_int(playlist_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid playlist ID! Expected integer in range: 1 to 9223372036854775807")

    consumer_id = user_id

    conn, cur = utils.db_connect()

    statement = """
                DELETE FROM playlists
                WHERE id = %s AND consumers_users_id = %s
                RETURNING id
                """
    values = (playlist_id, consumer_id)

    try:
        cur.execute(statement, values)
        rows = cur.fetchone()
        conn.commit()
        if not rows:
            flask.abort(utils.StatusCodes["not_found"], f"No playlist of your authorship found with ID {playlist_id}!")
        else:
            response = {"results": f"Playlist deleted with ID {playlist_id}!"}
    except psycopg2.DatabaseError:
        conn.rollback()
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/ban", methods=["POST"])
@requires_authentication(restrict = ["administrator"])
def ban_user(user_id, user_role):
    payload = flask.request.get_json()

    required = {"user_id", "reason", "end_time"}
    utils.payload_validate(payload, required)

    admin_id = user_id
    user_id = payload["user_id"]
    reason = payload["reason"]
    end_time = payload["end_time"]

    if not utils.integer_validate(user_id, min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid user ID! Expected integer in range: 1 to 9223372036854775807")
    if not utils.string_validate(reason, max_len = 512):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid reason! Expected string with length: 1 to 512")
    if end_time is not None and not utils.datetime_validate(end_time, "%Y-%m-%dT%H:%M:%S", future = True):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid end time! Expected null or future time string in ISO 8601 format: YYYY-MM-DDTHH:MM:SS")

    try:
        conn, cur = utils.db_connect()

        statement = """
                    SELECT end_time
                    FROM bans
                    WHERE users_id = %s AND (end_time > CURRENT_TIMESTAMP OR end_time IS NULL)
                    """
        values = (user_id,)
        cur.execute(statement, values)

        row = cur.fetchone()
        if row:
            end_time = row[0].strftime("%Y-%m-%d %H:%M:%S") if row[0] else "he is manually unbanned"
            flask.abort(utils.StatusCodes["bad_request"], f"User with ID {user_id} already has an active ban until {end_time}!")

        statement = """
                    INSERT INTO bans (administrators_users_id, users_id, reason, start_time, end_time, manual_unban)
                    SELECT %s, %s, %s, CURRENT_TIMESTAMP, %s, FALSE
                    WHERE NOT EXISTS (SELECT 1 FROM administrators WHERE users_id = %s)
                    RETURNING id
                    """
        values = (admin_id, user_id, reason, end_time, user_id)
        cur.execute(statement, values)

        row = cur.fetchone()
        if not row:
            flask.abort(utils.StatusCodes["bad_request"], "You cannot ban an administrator!")
        else:
            response = {"results": f"Ban added with ID {row[0]}!"}

        conn.commit()

    except werkzeug.exceptions.HTTPException:
        raise
    except psycopg2.errors.ForeignKeyViolation:
        flask.abort(utils.StatusCodes["bad_request"], f"No user found with ID {user_id}!")
    except Exception as e:
        print(e)
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/unban/<user_id>", methods=["PUT"])
@requires_authentication(restrict = ["administrator"])
def unban_user(request_user_id, request_user_role, user_id):
    if not utils.integer_validate(utils.string_to_int(user_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid user ID! Expected integer in range: 1 to 9223372036854775807")

    try:
        conn, cur = utils.db_connect()

        # Only set end time to current time for unban instead of delete so we keep a record of the ban
        statement = """
                    UPDATE bans
                    SET end_time = CURRENT_TIMESTAMP, manual_unban = TRUE
                    WHERE users_id = %s AND (end_time > CURRENT_TIMESTAMP OR end_time IS NULL)
                    RETURNING id
                    """
        values = (user_id,)
        cur.execute(statement, values)

        row = cur.fetchone()
        if not row:
            flask.abort(utils.StatusCodes["not_found"], f"No active ban found for user with ID {user_id}!")
        else:
            response = {"results": f"User with ID {row[0]} unbanned!"}

        conn.commit()

    except werkzeug.exceptions.HTTPException:
        raise
    except Exception:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/comment/<song_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_song_comments(user_id, user_role, song_id):
    # Verify that the song id is valid
    try:
        song_id = int(song_id)
        if song_id < 1 or song_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID!")

    conn, cur = utils.db_connect()

    statement = """
                SELECT id
                FROM comments
                WHERE songs_id = %s AND comments_id IS NULL
                ORDER BY id ASC;
                """
    values = (song_id,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"Song with ID {song_id} has no comments!"}
        else:
            results = []
            for row in rows:
                results.append({"comment_id": row[0]})
            response = {"results": results}
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/comment_info/<comment_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_comment_info(user_id, user_role, comment_id):
    # Verify that the comment id is valid
    try:
        comment_id = int(comment_id)
        if comment_id < 1 or comment_id > 9223372036854775807:
            raise ValueError
    except ValueError:
        flask.abort(utils.StatusCodes["bad_request"], "Invalid song ID!")

    conn, cur = utils.db_connect()

    statement = """
                SELECT comments.content, comments.post_time, consumers.display_name, replies.id
                FROM comments
                LEFT JOIN consumers ON comments.consumers_users_id = consumers.users_id
                LEFT JOIN comments AS replies ON comments.id = replies.comments_id
                WHERE comments.id = %s
                """
    values = (comment_id,)

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No comment found with ID {comment_id}!"}
        else:
            content, post_time, author = rows[0][:3]
            replies_comment_id = []
            for row in rows:
                if row[3]:
                    replies_comment_id.append(row[3])
            response = {"results":
                            {
                                "content": content,
                                "post_time": post_time,
                                "author": author,
                                "replies_comment_id": replies_comment_id if replies_comment_id else ["This comment has no replies!"]
                            }
                        }
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/album/<keyword>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_album(user_id, user_role, keyword):
    flask.abort(utils.StatusCodes["not_implemented"], "This endpoint is not implemented yet!")

@app.route("/dbproj/album_info/<album_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_album_info(user_id, user_role, album_id):
    flask.abort(utils.StatusCodes["not_implemented"], "This endpoint is not implemented yet!")

@app.route("/dbproj/playlist/<keyword>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_playlist(user_id, user_role, keyword):
    keyword = keyword.replace("+", " ")
    keyword = f"%{keyword}%"

    conn, cur = utils.db_connect()

    consumer_id = user_id

    statement = """
                SELECT id, name, consumers.display_name
                FROM playlists
                LEFT JOIN consumers ON playlists.consumers_users_id = consumers.users_id
                WHERE name ILIKE %s AND private = FALSE
                """
    # Add extra condition to return private playlists if user is premium
    if user_role == "premium consumer":
        statement += "OR (private = TRUE AND consumers_users_id = %s)"
        values = (keyword, consumer_id)
    else:
        values = (keyword,)

    keyword = keyword.replace("%", "")

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            if user_role == "premium consumer":
                response = {"results": f"No playlists found with keyword {keyword}!"}
            if user_role == "consumer":
                response = {"results": f"No playlists found with keyword {keyword}, remember that your private playlists are only avaliable with premium!"}
        else:
            results = []
            for row in rows:
                results.append({"playlist_id": row[0], "playlist_name": row[1], "creator": row[2]})
            response = {"results": results}
    except psycopg2.DatabaseError as e:
        print(e)
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/playlist_info/<playlist_id>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_playlist_info(user_id, user_role, playlist_id):
    if not utils.integer_validate(utils.string_to_int(playlist_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid playlist ID! Expected integer in range: 1 to 9223372036854775807")

    conn, cur = utils.db_connect()

    statement = """
                SELECT name, consumers.display_name, private, songs.title
                FROM playlists
                LEFT JOIN consumers ON playlists.consumers_users_id = consumers.users_id
                LEFT JOIN playlist_orders ON playlists.id = playlist_orders.playlists_id
                LEFT JOIN songs ON playlist_orders.songs_id = songs.id
                WHERE playlists.id = %s AND playlists.private = FALSE
                """
    # Add extra condition to return private playlists if user is premium
    if user_role == "premium consumer":
        statement += "OR (playlists.private = TRUE AND consumers_users_id = %s)"
        values = (playlist_id, user_id)
    else:
        values = (playlist_id,)

    statement += "\nGROUP BY name, consumers.display_name, playlists.private, songs.title"

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            if user_role == "premium consumer":
                response = {"results": f"No playlist found with ID {playlist_id}!"}
            if user_role == "consumer":
                response = {"results": f"No playlist found with ID {playlist_id}, remember that your private playlists are only avaliable with premium!"}
        else:
            playlist_name, author, private = rows[0][:3]
            song_names = []
            for row in rows:
                if row[3]:
                    song_names.append(row[3])
            response = {"results":
                            {
                                "playlist_name": playlist_name,
                                "creator": author,
                                "private": private,
                                "song_names": song_names if song_names else ["This playlist does not have any songs yet!"]
                            }
                        }
    except psycopg2.DatabaseError as e:
        print(e)
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/artist/<keyword>", methods=["GET"])
@requires_authentication(restrict = ["consumer", "administrator"])
def get_artist(user_id, user_role, keyword):
    keyword = keyword.replace("+", " ")
    keyword = f"%{keyword}%"

    conn, cur = utils.db_connect()

    statement = """
                SELECT users_id, stage_name
                FROM artists
                WHERE stage_name ILIKE %s
                ORDER BY stage_name ASC
                """
    values = (keyword,)

    keyword = keyword.replace("%", "")

    try:
        cur.execute(statement, values)
        rows = cur.fetchall()
        if not rows:
            response = {"results": f"No artists found with keyword {keyword}!"}
        else:
            results = []
            for row in rows:
                results.append({"artist_id": row[0], "stage_name": row[1]})
            response = {"results": results}
    except psycopg2.DatabaseError:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/comment/<starting_comment_id>", methods=["DELETE"])
@requires_authentication(restrict = ["consumer","administrator"])
def delete_comment_thread(user_id, user_role, starting_comment_id):
    if not utils.integer_validate(utils.string_to_int(starting_comment_id), min_val = 1, max_val = 9223372036854775807):
        flask.abort(utils.StatusCodes["bad_request"], "Invalid comment ID! Expected integer in range: 1 to 9223372036854775807")

    conn, cur = utils.db_connect()

    # User can only delete threads they started, administrators can delete any thread as part of moderation
    if user_role == "administrator":
        statement = """
                    DELETE FROM comments
                    WHERE id = %s
                    RETURNING id
                    """
        values = (starting_comment_id,)
    if user_role == "consumer" or user_role == "premium consumer":
        statement = """
                    DELETE FROM comments
                    WHERE id = %s AND consumers_users_id = %s
                    RETURNING id
                    """
        values = (starting_comment_id, user_id)

    try:
        cur.execute(statement, values)
        rows = cur.fetchone()
        conn.commit()
        if not rows:
            if user_role == "administrator":
                response = {"results": f"No comment found with ID {starting_comment_id}!"}
            if user_role == "consumer" or user_role == "premium consumer":
                response = {"results": f"No comment of your authorship found with ID {starting_comment_id}!"}
        else:
            response = {"results": f"Thread deleted starting with comment ID {starting_comment_id}!"}
    except (psycopg2.DatabaseError, psycopg2.IntegrityError, psycopg2.InternalError,
            psycopg2.ProgrammingError, psycopg2.DataError, psycopg2.NotSupportedError,
            psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.Error, psycopg2.Warning):
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")

    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.route("/dbproj/top10", methods=["GET"])
@requires_authentication(restrict = ["consumer"])
def get_my_top10(user_id, user_role):
    flask.abort(utils.StatusCodes["not_implemented"], "This endpoint is not implemented yet!")

@app.route("/dbproj/subscription", methods=["GET"])
@requires_authentication(restrict = ["consumer"])
def get_my_subscription(user_id, user_role):
    consumer_id = user_id

    try:
        conn, cur = utils.db_connect()


        statement = """
                    SELECT id, start_time, end_time
                    FROM subscriptions
                    WHERE consumers_users_id = %s AND end_time > CURRENT_TIMESTAMP
                    ORDER BY end_time DESC
                    """
        values = (consumer_id,)
        cur.execute(statement, values)

        rows = cur.fetchall()
        if not rows:
            response = {"results": "You have no active subscriptions!"}
        else:
            results = []
            for row in rows:
                results.append({"subscription_id": row[0], "start_time": row[1], "end_time": row[2]})
            response = {"results": results}

    except werkzeug.exceptions.HTTPException:
        raise
    except Exception:
        flask.abort(utils.StatusCodes["internal_error"], "Database failed to execute query!")
    finally:
        utils.db_disconnect(conn, cur)

    return flask.make_response(flask.jsonify(response), utils.StatusCodes["success"])

@app.errorhandler(400)
def bad_request(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(401)
def unauthorized(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(403)
def forbidden(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(404)
def page_not_found(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(405)
def method_not_allowed(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(429)
def too_many_requests(e):
    response = {"errors": f"You have made too many requests in a short time, limit is {e.description}, you must now wait this period before trying again!"}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(500)
def internal_error(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

@app.errorhandler(501)
def not_implemented(e):
    response = {"errors": e.description}
    return flask.make_response(flask.jsonify(response), e.code)

if __name__ == "__main__":
    # Load environment variables
    dotenv.load_dotenv()
    required_environment = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "SERVER_HOST", "SERVER_PORT", "SECRET_KEY"]
    for variable in required_environment:
        if variable not in os.environ:
            raise Exception(f"Missing environment variable: {variable}, make sure to place it in your .env file!")

    # Setup server
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    host = os.environ.get("SERVER_HOST")
    port = os.environ.get("SERVER_PORT")

    app.run(host = host, threaded = True, port = port)
