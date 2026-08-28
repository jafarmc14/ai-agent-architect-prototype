from configs import get_settings


def import_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "Missing PostgreSQL driver. Install it with: py -m pip install psycopg[binary]"
        ) from exc
    return psycopg, dict_row


def get_postgres_connection():
    settings = get_settings()
    if not settings.postgres_database_url:
        raise RuntimeError("DATABASE_URL is required when DATABASE_PROVIDER=postgres.")

    psycopg, dict_row = import_psycopg()
    return psycopg.connect(settings.postgres_database_url, row_factory=dict_row)
