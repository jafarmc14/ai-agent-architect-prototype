from configs import get_settings
from contextlib import contextmanager
from contextvars import ContextVar

_transaction_connection = ContextVar("mutation_connection", default=None)


class _BorrowedConnection:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *args):
        return False


@contextmanager
def mutation_transaction(key):
    if _transaction_connection.get() is not None:
        raise RuntimeError("Nested mutation transactions are not supported")
    with get_postgres_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
        token = _transaction_connection.set(conn)
        try:
            yield conn
        finally:
            _transaction_connection.reset(token)


def import_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "Missing PostgreSQL driver. Install it with: py -m pip install psycopg[binary]"
        ) from exc
    return psycopg, dict_row


def get_postgres_connection(*, tuple_rows=False, database_url=None):
    existing = _transaction_connection.get()
    if existing is not None:
        if tuple_rows or database_url:
            raise RuntimeError("Cross-connection work is not allowed within a mutation")
        return _BorrowedConnection(existing)
    settings = get_settings()
    if not settings.postgres_database_url:
        raise RuntimeError("DATABASE_URL is required when DATABASE_PROVIDER=postgres.")

    psycopg, dict_row = import_psycopg()
    from core.auth.request_context import get_request_context, is_request_scoped
    conn = psycopg.connect(database_url or settings.postgres_database_url,
                           **({} if tuple_rows else {"row_factory": dict_row}))
    try:
        tenant = get_request_context().tenant_id if is_request_scoped() else "default"
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        if is_request_scoped():
            from core.companies import company_config
            conn.execute("SELECT set_config('app.currency', %s, true)", (company_config().currency,))
            conn.execute("SET LOCAL ROLE ai_agent_runtime")
        return conn
    except BaseException:
        conn.close()
        raise
