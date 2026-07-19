"""Tests for the Prisma → Misata importer (misata/prisma_import.py)."""

import pandas as pd
import pytest

from misata.prisma_import import (
    build_schema_from_prisma,
    find_prisma_schema,
    parse_prisma,
)

SCHEMA = """
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

enum Role {
  USER
  ADMIN
  SUPPORT
}

enum OrderStatus {
  PLACED
  SHIPPED
  DELIVERED
  RETURNED
}

model User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  name      String
  role      Role     @default(USER)
  bio       String?
  createdAt DateTime @default(now())
  orders    Order[]
  reviews   Review[]
}

model Product {
  id       Int     @id @default(autoincrement())
  name     String
  price    Float
  sku      String  @unique
  reviews  Review[]
  items    OrderItem[]
}

model Order {
  id        Int         @id @default(autoincrement())
  user      User        @relation(fields: [userId], references: [id])
  userId    Int
  status    OrderStatus @default(PLACED)
  placedAt  DateTime
  items     OrderItem[]
}

model OrderItem {
  order     Order   @relation(fields: [orderId], references: [id])
  orderId   Int
  product   Product @relation(fields: [productId], references: [id])
  productId Int
  quantity  Int

  @@id([orderId, productId])
}

model Review {
  id        Int     @id @default(autoincrement())
  user      User    @relation(fields: [userId], references: [id])
  userId    Int
  product   Product @relation(fields: [productId], references: [id])
  productId Int
  stars     Int
  body      String?

  @@unique([userId, productId])
}
"""


def test_parse_models_and_enums():
    parsed = parse_prisma(SCHEMA)
    assert [m.name for m in parsed.models] == [
        "User", "Product", "Order", "OrderItem", "Review",
    ]
    assert parsed.enums["Role"] == ["USER", "ADMIN", "SUPPORT"]
    assert parsed.enums["OrderStatus"] == ["PLACED", "SHIPPED", "DELIVERED", "RETURNED"]

    user = parsed.models[0]
    by_name = {f.name: f for f in user.fields}
    assert by_name["id"].is_id
    assert by_name["email"].unique
    assert by_name["bio"].optional
    assert by_name["orders"].is_list and by_name["orders"].type == "Order"

    item = parsed.models[3]
    assert item.composite_ids == [["orderId", "productId"]]
    review = parsed.models[4]
    assert review.composite_uniques == [["userId", "productId"]]


def test_translation():
    schema, report = build_schema_from_prisma(SCHEMA, rows=100)

    assert sorted(t.name for t in schema.tables) == [
        "Order", "OrderItem", "Product", "Review", "User",
    ]
    # Relation object fields never become columns
    assert "orders" not in {c.name for c in schema.columns["User"]}

    rels = {(r.parent_table, r.child_table, r.child_key) for r in schema.relationships}
    assert ("User", "Order", "userId") in rels
    assert ("Order", "OrderItem", "orderId") in rels
    assert ("Product", "OrderItem", "productId") in rels
    assert ("User", "Review", "userId") in rels
    assert ("Product", "Review", "productId") in rels
    assert report.relationships == 5

    user_cols = {c.name: c for c in schema.columns["User"]}
    assert user_cols["role"].type == "categorical"
    assert user_cols["role"].distribution_params["choices"] == ["USER", "ADMIN", "SUPPORT"]
    assert user_cols["email"].unique
    assert user_cols["bio"].nullable

    item_table = next(t for t in schema.tables if t.name == "OrderItem")
    combos = {tuple(c.group_by) for c in item_table.constraints
              if c.type == "unique_combination"}
    assert ("orderId", "productId") in combos
    review_table = next(t for t in schema.tables if t.name == "Review")
    combos_r = {tuple(c.group_by) for c in review_table.constraints
                if c.type == "unique_combination"}
    assert ("userId", "productId") in combos_r
    assert report.composite_constraints == 2


def test_generated_data_satisfies_prisma_contract():
    from misata.simulator import DataSimulator

    schema, _ = build_schema_from_prisma(SCHEMA, rows=200, seed=5)
    sim = DataSimulator(schema)
    tables: dict = {}
    for name, batch in sim.generate_all():
        tables[name] = pd.concat([tables[name], batch], ignore_index=True) \
            if name in tables else batch

    users, orders, items, reviews, products = (
        tables["User"], tables["Order"], tables["OrderItem"],
        tables["Review"], tables["Product"],
    )

    # @id / @unique
    assert users["id"].is_unique
    assert users["email"].is_unique
    assert products["sku"].is_unique

    # enums restricted to declared values
    assert set(users["role"]).issubset({"USER", "ADMIN", "SUPPORT"})
    assert set(orders["status"]).issubset({"PLACED", "SHIPPED", "DELIVERED", "RETURNED"})

    # @relation FK integrity
    assert set(orders["userId"]).issubset(set(users["id"]))
    assert set(items["orderId"]).issubset(set(orders["id"]))
    assert set(items["productId"]).issubset(set(products["id"]))
    assert set(reviews["userId"]).issubset(set(users["id"]))
    assert set(reviews["productId"]).issubset(set(products["id"]))

    # composite constraints hold
    assert not items.duplicated(["orderId", "productId"]).any()
    assert not reviews.duplicated(["userId", "productId"]).any()


def test_missing_models_raises():
    with pytest.raises(ValueError):
        build_schema_from_prisma("datasource db { provider = \"sqlite\" }")


def test_find_prisma_schema(tmp_path):
    (tmp_path / "prisma").mkdir()
    target = tmp_path / "prisma" / "schema.prisma"
    target.write_text("model A { id Int @id }")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    assert find_prisma_schema(nested) == target
    assert find_prisma_schema(tmp_path) == target
