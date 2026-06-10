"""Guards against the obvious 'this data is fake' tells, fixed for 0.8.0.2.

Covers: product name vs category coherence, and the row-count-misread-as-year bug
("2000 customers" must not date the dataset to the year 2000).
"""
import warnings
import pandas as pd
import misata
import misata.realism as r
from misata.story_parser import StoryParser

warnings.filterwarnings("ignore")


class TestProductCategoryCoherence:
    def test_product_names_match_category(self):
        t = misata.generate("An ecommerce store with 2000 customers and products", rows=2000, seed=7)
        prod = t["products"]
        bad = 0
        for nm, cat in zip(prod["name"], prod["category"]):
            pool = r._NAME_TO_POOL.get(str(nm))
            if pool is None:
                continue
            cl = str(cat).lower()
            if not (pool in cl or cl in pool or pool in cl.split()):
                bad += 1
        assert bad == 0, f"{bad} product name/category mismatches"


class TestYearExtraction:
    def setup_method(self):
        self.p = StoryParser()

    def test_row_count_not_read_as_year(self):
        # "2000 customers" is a count, not the year 2000
        assert self.p._extract_explicit_year("2000 customers, Black Friday") is None
        assert self.p._extract_explicit_year("5000 users") is None
        assert self.p._extract_explicit_year("2015 orders this month") is None

    def test_real_year_is_detected(self):
        assert self.p._extract_explicit_year("revenue in 2023, 1000 orders") == 2023
        assert self.p._extract_explicit_year("data for 2024 with 3000 users") == 2024

    def test_no_dataset_dated_to_year_2000(self):
        t = misata.generate("An ecommerce store with 2000 customers, orders, Black Friday peak",
                            rows=1500, seed=7)
        for name, df in t.items():
            for col in df.columns:
                if "date" in col.lower() or col.endswith("_at"):
                    yrs = pd.to_datetime(df[col], errors="coerce").dt.year.dropna()
                    if len(yrs):
                        assert yrs.min() >= 2015, f"{name}.{col} dated to {int(yrs.min())}"

    def test_child_dates_within_parent_range(self):
        # orders should fall within the customer signup range, not before it
        t = misata.generate("An ecommerce store with 2000 customers and orders, Black Friday peak",
                            rows=2000, seed=7)
        cust_yrs = set(pd.to_datetime(t["customers"]["signup_date"]).dt.year)
        ord_dcol = "order_date" if "order_date" in t["orders"].columns else "ordered_at"
        ord_yrs = set(pd.to_datetime(t["orders"][ord_dcol]).dt.year)
        assert min(ord_yrs) >= min(cust_yrs)
