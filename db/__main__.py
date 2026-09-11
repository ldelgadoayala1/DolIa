"""
Inicializa el esquema y siembra el catálogo de proveedores.

Uso (desde el host, con docker-compose):
    docker compose run --rm api python -m db
"""

from . import init_db, seed_providers

if __name__ == "__main__":
    print("[db] creando tablas...")
    init_db()
    print("[db] sembrando catálogo de proveedores...")
    seed_providers()
    print("[db] listo.")
