import flask
import logging
import psycopg2
import datetime
import random
import os

app = flask.Flask(__name__)

StatusCodes = {
    'success': 200,
    'api_error': 400,
    'internal_error': 500
}

def db_connection():
    db = psycopg2.connect(
        user='aulaspl',
        password='aulaspl',
        host='127.0.0.1',
        port='5432',
        database='dbfichas'
    )
    return db

# TODO birthday e gender são uma complicação de merda, acho que é preferivel tirar, visto que n sao relevantes
# TODO Add consumer? os consumers n deveriam ser users? Cagávamos naquilo de addresses
# e assim porque n é informação relevante e faziamos premium = bool

# TODO usar isto para datas ? datetime.date.today().isoformat()

# ==@=== REGISTRATIONS ===@==
@app.route('/user/', methods=['POST'])
def user_registration():
    logger.info('POST /user')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    if 'username' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'username value not in payload'}
        return flask.jsonify(response)

    # TODO remove gender | criar artista usando admin ?
    statement = 'INSERT INTO user (username, password, full_name, birthday, email) VALUES (%s, %s, %s, %s, %s)'
    values = (payload['username'], payload['password'], payload['full_name'], payload['birthday'], payload['email'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted user {payload["username"]}'}

    # an error occurred, rollback
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /user/ - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}
        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


@app.route('/administrator/', methods=['POST'])
def admin_registration():
    logger.info('POST /administrator')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    if 'username' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'username value not in payload'}
        return flask.jsonify(response)

    statement = 'INSERT INTO administrator (username) VALUES (%s)'
    values = (payload['username'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted user {payload["username"]}'}

    # an error occurred, rollback
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /administrator/ - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}
        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


@app.route('/artist/', methods=['POST'])
#@token_required
def artist_registration():
    logger.info('POST /artist')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    if 'username' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'username value not in payload'}
        return flask.jsonify(response)

    # TODO admin e userr_username podem ser desnecessários para criar || Also int para ismn estará correto?
    statement = 'INSERT INTO artist (artistic_name, song_ismn, label_name, administrator_u, userr_username) VALUES (%s, %d, %s, %s, %s)'
    values = (payload['artistic_name'], int(payload['song_ismn']), payload['label_name'], payload['administrator_u'], payload['userr_username'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted user {payload["username"]}'}

    # an error occurred, rollback
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /artist/ - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}
        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


# ==@=== AUTHENTICATIONS ===@==
@app.route("/user/", methods = ['PUT'])
def user_authentication():
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.info("AUTENTICATE /user")
    logger.debug(f'payload: {payload}')

    cur.execute("SELECT password FROM user WHERE username=%s", (payload["username"],))
    logger.debug(f'payload: {payload["username"]}')

    password = cur.fetchall()
    if (len(password) == 0):
        result = {"Error:": "Invalid Login"}
        return flask.jsnofiy(result)

    if (password[0][0] != payload["password"]):
        result = {"Error": "Invalid Login"}
        if conn is not None:
            conn.close()
        return flask.jsnofiy(result)

    # TODO isto estava no meu do ano passado
    # token = jwt.encode({'iduser': payload["iduser"],'exp': datetime.utcnow() + timedelta(minutes = 30)}, app.config['SECRET_KEY'], algorithm = "HS256")


@app.route("/administrator/", methods=['PUT'])
def admin_authentication():
    # TODO fazer autenticação do admin (assumo que tenhamos de ver se o utilizador está na tabela
    # dos admins e depois ver se a passe bate certo na tabela dos users)
    payload = flask.request.get_json()


@app.route("/artist/", methods=['PUT'])
def artist_authentication():
    # TODO fazer algo semelhante do admin, so que ver se o username está na tabela
    # dos artistas e depois comparar com a pass na tabela dos users
    payload = flask.request.get_json()


# ==@=== GETs ===@==
@app.route("/user/", methods=['GET'])
def get_all_users():
    logger.info('GET /user')
    payload = flask.flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    statement = 'SELECT * from user'
    cur.execute(statement)
    rows = cur.fetchall()

    payload = []

    for row in rows:
        logger.debug(row)
        content = {'username': row[0], 'password': row[1], 'full_name': row[2], 'email': row[3]}
        payload.append(content)

    response = {'status': StatusCodes['success'], 'results': payload}

    conn.close()

    return flask.jsonify(response)


@app.route("/song/<keyword>", methods=['GET'])
def search_song(keyword):
    conn = db_connection()
    cur = conn.cursor()

    # FIXME i think its fine this way
    cur.execute("SELECT ismn, title, genre from song where ismn = %s or title = %s or genre = %s", (keyword, keyword, keyword))

    rows = cur.fetchall()

    payload = []
    logger.debug("Songs:")

    for row in rows:
        content = {'ismn': int(row[0]), 'title': row[1], 'genre': row[2]}
        payload.append(content)
        logger.debug(row)

    conn.close()

    return flask.jsnofiy(payload)


@app.route("/artist/<name>", methods=['GET'])
def detail_artist(name):
    conn = db_connection()
    cur = conn.cursor()

    # TODO n está acabada, é preciso fazer mais cenas ig
    cur.execute("SELECT label_name from artist where artistic_name = %s UNION select title from album where artist_userr = %s", (name, name))

    rows = cur.fetchall()

    payload = []
    logger.debug("Artist Details:")

    for row in rows:
        content = {'Artist Name': name, 'label_name': row[0]}
        payload.append(content)
        logger.debug(row)

    conn.close()

    return flask.jsnofiy(payload)


@app.route("/stream/<ismn>", methods=['GET'])
def get_streams(ismn):
    logger.info('GET /stream')
    payload = flask.flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    # TODO acho que este statemente funciona bem
    statement = 'SELECT COUNT (stream_data) from stream where song_ismn = %s', ismn
    cur.execute(statement)
    rows = cur.fetchall()

    payload = []

    for row in rows:
        logger.debug(row)
        content = {'n_streams': row[0]}
        payload.append(content)

    response = {'status': StatusCodes['success'], 'results': payload}

    conn.close()

    return flask.jsonify(response)


# ==@=== FUNCTIONALITIES ===@==
@app.route("/song/", methods=['POST'])
#@token_required
def add_song():
    logger.info('POST /song/')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.debug(f'POST /song - payload: {payload}')

    if 'ismn' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'ismn value not in payload'}
        return flask.jsonify(response)

    # FIXME isto com ints e assim está a confundir-me um pouco, no meu do ano passado temos tudo como %s
    statement = 'INSERT INTO song (ismn, title, genre, duration, release_date, explicit)' \
                'values (%d, %s, %s, %s, %s, %s)'
    values = (int(payload['ismn']), payload['title'], payload['genre'], payload['duration'],
              datetime.date.today().isoformat(), payload['explicit'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted song {payload["ismn"]}'}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /song - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


@app.route("/album/", methods=['POST'])
#@token_required
def add_album():
    # TODO kinda confused on this one
    # é preciso inserir logo uma musica? Ou quando criamos uma musica criamos um album?
    # E como se usa a order?
    logger.info('POST /album/')
    payload = flask.request.get_json()


@app.route("/playlist/", methods=['POST'])
#@token_required
def create_playlist():
    logger.info('POST /playlist/')
    payload = flask.request.get_json()
    conn = db_connection()
    cur = conn.cursor()

    logger.debug(f'POST /song - payload: {payload}')

    if 'name' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'ismn value not in payload'}
        return flask.jsonify(response)

    # FIXME list of tracks to add to playlist
    statement = 'INSERT INTO playlist (id, name, visibility, consumer_userr)' \
                'values (%d, %s, %s, %s)'
    values = (random.randint(0, 1000), payload['name'], payload['visibility'], payload['consumer_userr'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Created playlist {payload["name"]}'}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /playlist - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


@app.route("/stream/<ismn>", methods=['POST']) # FIXME not sure se o address está correto
#@token_required # TODO Tem de estar logado ig
def play_song(ismn):
    logger.info('POST /stream/')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.debug(f'POST /stream - payload: {payload}')

    if 'ismn' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'ismn value not in payload'}
        return flask.jsonify(response)

    # FIXME isto com ints e assim está a confundir-me um pouco, no meu do ano passado temos tudo como %s
    # TODO acho que as datas assim devem funcionar
    statement = 'INSERT INTO stream (ismn, stream_date, consumer_userr)' \
                'values (%d, %s, %s)'
    values = (int(payload['ismn']), datetime.date.today().isoformat(), payload['consumer_userr'])

    try:
        cur.execute(statement, values)
        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted stream {payload["ismn"]}'}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /stream - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


# ==@=== MAIN ===@==
if __name__ == '__main__':

    # set up logging
    try:
        os.makedirs("logs")
    except FileExistsError:
        pass
    log = "/logs" + datetime.date.today().isoformat() + ".log"
    logging.basicConfig(filename=log)
    logger = logging.getLogger("LOGGER:")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s]:  %(message)s', '%H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    #set up server
    host = '127.0.0.1'
    port = 8080
    app.run(host=host, debug=True, threaded=True, port=port)

    logger.info(f'API v1.0 online: http://{host}:{port}')
