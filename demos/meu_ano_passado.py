import logging, psycopg2, time
import flask
import logging
from flask import jsonify
from flask import request
import jwt
from datetime import datetime, timedelta

app = flask.Flask(__name__)

StatusCodes = {
    'success': 200,
    'api_error': 400,
    'internal_error': 500
}


# Connect to DB
def db_connection():
    db = psycopg2.connect(
        user="aulaspl",
        password="aulaspl",
        host="localhost",
        port="5432",
        database="project"
    )

    return db


# Add user to DB
@app.route("/dbproj/user", methods=['POST'])
def add_user():
    logger.info('POST /user')

    payload = request.get_json()

    conn = db_connection()

    if conn is None:
        response = {'status': StatusCodes['api_error'], 'errors': 'Connection to database failed'}
        return jsonify(response)

    cur = conn.cursor()

    logger.info("---- NEW USER ----")
    logger.debug(f'POST /user - payload: {payload}')

    if 'username' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'username value not in payload'}
        return flask.jsonify(response)

    # parameterized queries, good for security and performance
    statement = "INSERT INTO utilizador (username, passworduser, iduser, nameuser, isadmin) VALUES (%s, %s, %s, %s, %s)"
    values = (payload["username"], payload["passworduser"], payload["iduser"], payload['nameuser'], payload['isadmin'])

    try:
        cur.execute(statement, values)
        cur.execute("commit")
        result = 'INSERTED'
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(error)
        result = 'FAILED'
    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(result)


# User autentication
@app.route("/dbproj/user", methods = ['PUT'])
def autenticate_user():
    payload = request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.info("AUTENTICATE /USER")
    logger.debug(f'payload: {payload}')

    cur.execute("SELECT passworduser FROM utilizador WHERE username=%s", (payload["username"],))
    logger.debug(f'payload: {payload["username"]}')

    password = cur.fetchall()
    if (len(password) == 0):
        result = {"Erro:": "Login Invalido"}
        return jsonify(result)

    if (password[0][0] != payload["passworduser"]):
        result = {"Erro": "Login Invalido"}
        if conn is not None:
            conn.close()
        return jsonify(result)

    token = jwt.encode({'iduser': payload["iduser"],'exp': datetime.utcnow() + timedelta(minutes = 30)}, app.config['SECRET_KEY'], algorithm = "HS256")

    return jsonify({'token': token})


# Get all users
@app.route("/user/", methods=['GET'])
def get_all_users():
    logger.info("GET /USER")

    conn = db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * from utilizadores")
    rows = cur.fetchall()

    payload = []
    logger.debug("---- ALL USERS ----")
    for row in rows:
        logger.debug(row)
        content = {'username': int(row[0]), 'password': row[1], 'iduser': row[2], 'name': row[3]}
        payload.append(content)  # appending to the payload to be returned

    if conn is not None:
        conn.close()

    return flask.jsonify(payload)


# Add new product
@app.route("/dbproj/product", methods=['POST'])
def add_product():
    logger.info('POST /product/')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.debug(f'POST /product - payload: {payload}')

    if 'idproduct' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'idproduct value not in payload'}
        return flask.jsonify(response)

    statement = 'insert into produto (idproduct, productname, producttype, description, productprice, productstock)' \
                'values (%s, %s, %s, %s, %s, %s)'
    values = (payload['idproduct'], payload['productname'], payload['producttype'], payload['description'],
              payload['productprice'], payload['productstock'])

    try:
        cur.execute(statement, values)

        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted produto {payload["idproduct"]}'}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /produtos - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}

        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


# Update product
@app.route("/products/update/<id>", methods=['POST'])
def update_product(id, description):
    logger.info('POST /product/update/')
    payload = flask.request.get_json()

    conn = db_connection()
    cur = conn.cursor()

    logger.info('---- UPDATE PRODUCT ----')
    logger.info(f'payload: {payload}')

    cur = conn.cursor()

    cur.execute('select productname,description,id where produtos.id=%s and produtos.description=%s', (id, description))

    row = cur.fetchall()

    if cur.rowcount == 0:
        conn.close()
        logger.error(f'POST /produtos - error: {logging.error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(logging.error)}

    statement = "update produtos set productprice=%s,productstock=%s,"


#Generic product information
@app.route("/dbproj/product/<product_id>", methods=['GET'])
def productInfo(id):
    conn = db_connection()
    cur = conn.cursor()

    cur.execute("SELECT idproduct, description from produtos where idproduct = %s and produtos.description = %s", (id,))

    rows = cur.fetchall()
    cur.execute("SELECT texto,data_user_username from mensagem_mural where leiloes_id_leilao=%s", (id,))

    payload = []
    logger.debug("Products:")

    for row in rows:
         content = {'idproduct': int(row[0]), 'description': row[1]}
         payload.append(content)
         logger.debug(row)

    conn.close()

    return jsonify(payload)


#Purchase product____________________________________Terminar_____________________________
@app.route('/dbproj/order', methods = ['PUT'])
def purchase():
    token = request.headers.get('authtoken')

    if token is None:
        response = {'status': StatusCodes['req_error'], 'errors': 'Authentication token missing'}
    else:
        userinfo = jwt.decode(token, "SECRET_KEY", algorithms = "HS256")

    payload = request.get_json()
    required = {'encomenda'}

    fields = set(payload.keys())
    diff = list(required.difference(fields))

    if (len(diff) > 0):
        response = {'status': StatusCodes['req_error'], 'errors': f'Missing fields {diff}'}
        return jsonify(response)

    encomenda = payload["encomenda"]

    conn = db_connection()

    try:
        conn.cursor().execute("BEGIN")
        conn.cursor().execute("SELECT FROM comprador WHERE iduser = %s", (userinfo['iduser'],))

        if (conn.cursor().fetchone() is None):
            response = {'status': StatusCodes['req_error'], 'errors': 'User registered is not a buyer'}
            return jsonify(response)
        else:
            conn.cursor().execute("SELECT balance FROM user WHERE iduser = %s", (userinfo['iduser'],))
            balance = conn.cursor().fetchone()
            idPurchase = idGenerator()

    except psycopg2.Error as e:
        response = {'status': StatusCodes['api_error'], 'errors': str(e)}

    return jsonify(response)


#Functions
def idGenerator(colum, table):
    conn = db_connection()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT({colum}) FROM {table}")
    result = cursor.fetchone()

    if result[0] is None:
        return 0

    return result[0] + 1


def main():
    # Set up the logging
    logging.basicConfig(filename="log_file.log")
    logger = logging.getLogger('logger')
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s]:  %(message)s', '%H:%M:%S')
    # "%Y-%m-%d %H:%M:%S") # not using DATE to simplify
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    time.sleep(1)  # just to let the DB start before this print :-)

    logger.info("\n---------------------------------------------------------------\n" +
                        "API v1.0 online: http://localhost:8080\n\n")

    app.run(host="0.0.0.0", debug=True, threaded=True, port=8080)


if __name__ == "__main__":
    main()