import os
import pyodbc

_connection = None


def get_connection():
    """
    Returns a reusable pyodbc connection, creating one if it doesn't exist
    or if the existing one has gone stale (Azure SQL can close idle connections).
    Reused across invocations within the same Function App instance, rather than
    opening/closing a fresh connection per request.
    """
    global _connection

    if _connection is not None:
        try:
            _connection.cursor().execute("SELECT 1")
            return _connection
        except pyodbc.Error:
            _connection = None

    conn_str = os.environ["SQL_CONNECTION_STRING"]
    _connection = pyodbc.connect(conn_str)
    return _connection