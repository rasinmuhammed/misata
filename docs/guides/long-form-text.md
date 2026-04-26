---
title: "Long-Form Text — Reviews, Support Tickets, and Email Bodies"
description: "Generate realistic multi-sentence text for product reviews, customer support tickets, and email messages — not Lorem Ipsum."
---

# Long-Form Text

Misata generates realistic multi-sentence text for content that needs to feel human — product reviews, support tickets, email bodies, social captions, and bios. None of it is Lorem Ipsum.

## Supported text types

| `text_type` | Format | Use case |
|---|---|---|
| `review` | 1–2 sentences, sentiment-weighted | Product/service review columns |
| `support_ticket` | Issue description + context | Helpdesk, CRM, support systems |
| `email_body` | Greeting + body + closing | Email datasets, inbox simulations |
| `caption` | Emoji + hashtag style | Social media posts |
| `bio` | Role \| vibe \| optional emoji | Social media user profiles |
| `comment_body` | Short reaction | Social comments, forum replies |
| `description` | Product feature sentence | E-commerce, catalog data |

## Reviews

```python
Column(name="review_text", type="text", distribution_params={"text_type": "review"})
```

Reviews are sentiment-weighted: 65% positive, 22% neutral, 13% negative — matching real platform distributions.

Sample output:
```
Great experience overall. Instructions could be clearer. Highly recommend.
Disappointing. Had a minor issue at first but it resolved quickly. Expected much better.
Absolutely loved it! The build quality feels premium. Will definitely come back.
```

Reviews are automatically detected for columns named `review`, `review_text`, or `review_body`.

## Support tickets

```python
Column(name="issue_body", type="text", distribution_params={"text_type": "support_ticket"})
```

Sample output:
```
I'm unable to log into my account after the recent update. I've tried clearing cache and it didn't help.
The payment keeps failing at checkout — tried three different cards. This is blocking my team from completing their work.
My order shows as delivered but I haven't received anything. Please escalate — this is urgent.
```

Auto-detected for columns named `ticket_body`, `issue_body`, or `description` in tables named `tickets`, `issues`, or `support_*`.

## Email bodies

```python
Column(name="message_body", type="text", distribution_params={"text_type": "email_body"})
```

Sample output:
```
Hi,

I wanted to follow up on our conversation from last week. Could you share an update?

Best regards,
```

Auto-detected for columns named `email_body`, `message_body`, or `body` in tables named `emails`, `messages`, or `inbox`.

## Social captions

```python
Column(name="caption", type="text", distribution_params={"text_type": "caption"})
```

Sample output:
```
loving every moment of this golden journey ✨ #instagood #travel #lifestyle #authentic
no filter needed when the hustle is this good 🌿 #daily #instagood #love
```

## Bios

```python
Column(name="bio", type="text", distribution_params={"text_type": "bio"})
```

Sample output:
```
Developer | building in public 🚀
Writer | sharing what I love
Photographer | exploring the world 🌍
```

## Full example: review dataset

```python
from misata.schema import SchemaConfig, Table, Column, Relationship

schema = SchemaConfig(
    name="Product Reviews",
    tables=[
        Table(name="products", row_count=100),
        Table(name="reviews",  row_count=2000),
    ],
    columns={
        "products": [
            Column(name="product_id", type="int", unique=True, distribution_params={"min": 1, "max": 101}),
            Column(name="name",       type="text", distribution_params={"text_type": "product_name"}),
            Column(name="category",   type="categorical", distribution_params={
                "choices": ["electronics", "clothing", "home", "sports"],
                "probabilities": [0.35, 0.30, 0.20, 0.15],
            }),
        ],
        "reviews": [
            Column(name="review_id",   type="int", unique=True, distribution_params={"min": 1, "max": 2001}),
            Column(name="product_id",  type="foreign_key"),
            Column(name="rating",      type="float", distribution_params={
                "distribution": "beta", "a": 4.0, "b": 1.5, "min": 1.0, "max": 5.0, "decimals": 1,
            }),
            Column(name="review_text", type="text", distribution_params={"text_type": "review"}),
            Column(name="verified",    type="boolean", distribution_params={"probability": 0.78}),
            Column(name="created_at",  type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
        ],
    },
    relationships=[
        Relationship(parent_table="products", child_table="reviews",
                     parent_key="product_id", child_key="product_id"),
    ],
)

import misata
tables = misata.generate_from_schema(schema)
print(tables["reviews"][["rating", "review_text"]].head(5).to_string())
```
