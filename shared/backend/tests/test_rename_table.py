from sqlalchemy import create_engine, inspect, text

from sn_shared.db import rename_table


def test_an_old_table_is_renamed_once_and_an_existing_new_one_is_left_alone():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO products (id) VALUES (7)"))
    rename_table(engine, "products", "market_products")
    tables = set(inspect(engine).get_table_names())
    assert "market_products" in tables and "products" not in tables
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM market_products")).scalar() == 7
    rename_table(engine, "products", "market_products")  # nothing to do the second time
    assert set(inspect(engine).get_table_names()) == tables
