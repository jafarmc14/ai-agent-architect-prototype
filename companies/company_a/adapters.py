def build_connectors():
    from configs import get_settings
    from companies.demo.adapters import build_connectors as demo_connectors
    if get_settings().database_provider != "postgres":
        raise PermissionError("Multi-company data requires PostgreSQL RLS")
    return demo_connectors()
