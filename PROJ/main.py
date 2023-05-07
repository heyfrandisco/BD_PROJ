import flask
import logging
import psycopg2
import time

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



# Add artist (or should I add/update a user)
@app.route('/artist/', methods=['POST'])
def add_artist():
    logger.info("POST /artist")
    payload = flask.request.get_json()

    conn = db_connection()
    cursor = conn.cursor()

    logger.debug(f'POST /artist - payload: {payload}')

    if 'artistic_name' not in payload:
        response = {'status': StatusCodes['api_error'], 'results': 'artist_name value not in payload'}
        return flask.jsonify(response)

    # TODO finish statement
    statement = 'insert into artist (artist_name) values(%s)'
    values = (payload['artist_name'])

    try:
        cursor.execute(statement, values)

        conn.commit()
        response = {'status': StatusCodes['success'], 'results': f'Inserted artist {payload["artist_name"]}'}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /artist - error: {error}')
        response = {'status': StatusCodes['internal_error'], 'errors': str(error)}

        # an error occurred, rollback
        conn.rollback()

    finally:
        if conn is not None:
            conn.close()

    return flask.jsonify(response)


if __name__ == '__main__':

    # set up logging
    logging.basicConfig(filename='log_file.log')
    logger = logging.getLogger('logger')
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s]:  %(message)s', '%H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    host = '127.0.0.1'
    port = 8080
    app.run(host=host, debug=True, threaded=True, port=port)
    logger.info(f'API v1.0 online: http://{host}:{port}')
