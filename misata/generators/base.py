"""
Base generator interface and factory for Misata.

Provides abstract base class for all generators and a factory
pattern for creating generators based on column type.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type, Union

import numpy as np

from misata.exceptions import ColumnGenerationError


class BaseGenerator(ABC):
    """Abstract base class for all data generators.
    
    All generators must implement the `generate` method which produces
    a numpy array of values.
    
    Example:
        class IntegerGenerator(BaseGenerator):
            def generate(self, size: int, params: dict) -> np.ndarray:
                return np.random.randint(params['min'], params['max'], size)
    """
    
    @abstractmethod
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        """Generate an array of values.
        
        Args:
            size: Number of values to generate
            params: Distribution parameters specific to this generator
            
        Returns:
            numpy array of generated values
            
        Raises:
            ColumnGenerationError: If generation fails
        """
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters before generation.
        
        Override this method to add custom validation.
        
        Args:
            params: Parameters to validate
            
        Raises:
            ColumnGenerationError: If validation fails
        """
        pass
    
    def inject_nulls(
        self, 
        values: np.ndarray, 
        null_rate: float = 0.0,
        rng: Optional[np.random.Generator] = None
    ) -> np.ndarray:
        """Inject null values into generated data.
        
        Args:
            values: Generated values array
            null_rate: Fraction of values to make null (0.0 to 1.0)
            rng: Random number generator for reproducibility
            
        Returns:
            Array with nulls injected (converted to object dtype if needed)
        """
        if null_rate <= 0:
            return values
        
        if rng is None:
            rng = np.random.default_rng()
            
        mask = rng.random(len(values)) < null_rate
        
        # Convert to object dtype to support None values
        result = values.astype(object)
        result[mask] = None
        
        return result
    
    def inject_outliers(
        self,
        values: np.ndarray,
        outlier_rate: float = 0.0,
        multiplier: float = 3.0,
        rng: Optional[np.random.Generator] = None
    ) -> np.ndarray:
        """Inject outlier values into numeric data.
        
        Args:
            values: Generated numeric values
            outlier_rate: Fraction of values to make outliers (0.0 to 1.0)
            multiplier: How many std devs to offset outliers
            rng: Random number generator for reproducibility
            
        Returns:
            Array with outliers injected
        """
        if outlier_rate <= 0 or not np.issubdtype(values.dtype, np.number):
            return values
            
        if rng is None:
            rng = np.random.default_rng()
            
        mask = rng.random(len(values)) < outlier_rate
        n_outliers = mask.sum()
        
        if n_outliers == 0:
            return values
            
        mean = np.mean(values)
        std = np.std(values)
        
        if std == 0:
            std = 1.0  # Avoid division by zero
        
        # Generate outliers at mean ± multiplier * std
        outlier_values = mean + rng.choice([-1, 1], n_outliers) * multiplier * std
        
        result = values.copy()
        result[mask] = outlier_values
        
        return result
    
    def post_process(
        self,
        values: np.ndarray,
        params: Dict[str, Any],
        rng: Optional[np.random.Generator] = None
    ) -> np.ndarray:
        """Apply post-processing: nulls, outliers, etc.
        
        Args:
            values: Generated values
            params: Parameters including null_rate, outlier_rate
            rng: Random number generator
            
        Returns:
            Post-processed values
        """
        null_rate = params.get("null_rate", 0.0)
        outlier_rate = params.get("outlier_rate", 0.0)
        
        # Apply outliers first (on numeric data)
        if outlier_rate > 0:
            values = self.inject_outliers(values, outlier_rate, rng=rng)
        
        # Apply nulls last
        if null_rate > 0:
            values = self.inject_nulls(values, null_rate, rng=rng)
        
        return values


class IntegerGenerator(BaseGenerator):
    """Generator for integer values with various distributions."""
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        distribution = params.get("distribution", "uniform")
        
        if distribution == "sequence":
            start = params.get("start", 1)
            return np.arange(start, start + size)
        
        elif distribution == "uniform":
            min_val = params.get("min", 0)
            max_val = params.get("max", 100)
            return np.random.randint(min_val, max_val + 1, size)
        
        elif distribution == "normal":
            mean = params.get("mean", 50)
            std = params.get("std", 10)
            return np.clip(np.random.normal(mean, std, size).astype(int), 0, None)
        
        elif distribution == "poisson":
            lam = params.get("lambda", 5)
            return np.random.poisson(lam, size)
        
        elif distribution == "binomial":
            n = params.get("n", 10)
            p = params.get("p", 0.5)
            return np.random.binomial(n, p, size)
        
        else:
            raise ColumnGenerationError(
                f"Unknown integer distribution: {distribution}",
                column_type="int",
                suggestion="Use 'uniform', 'normal', 'poisson', 'binomial', or 'sequence'"
            )


class FloatGenerator(BaseGenerator):
    """Generator for floating-point values with various distributions."""
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        distribution = params.get("distribution", "uniform")
        decimals = params.get("decimals", 2)
        
        if distribution == "uniform":
            min_val = params.get("min", 0.0)
            max_val = params.get("max", 100.0)
            values = np.random.uniform(min_val, max_val, size)
        
        elif distribution == "normal":
            mean = params.get("mean", 50.0)
            std = params.get("std", 10.0)
            values = np.random.normal(mean, std, size)
        
        elif distribution == "exponential":
            scale = params.get("scale", 1.0)
            values = np.random.exponential(scale, size)
        
        elif distribution == "lognormal":
            mean = params.get("mean", 0.0)
            sigma = params.get("sigma", 1.0)
            values = np.random.lognormal(mean, sigma, size)
        
        elif distribution == "beta":
            a = params.get("a", 2.0)
            b = params.get("b", 5.0)
            values = np.random.beta(a, b, size)
        
        else:
            raise ColumnGenerationError(
                f"Unknown float distribution: {distribution}",
                column_type="float",
                suggestion="Use 'uniform', 'normal', 'exponential', 'lognormal', or 'beta'"
            )
        
        return np.round(values, decimals)


class BooleanGenerator(BaseGenerator):
    """Generator for boolean values."""
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        probability = params.get("probability", 0.5)
        return np.random.random(size) < probability


class CategoricalGenerator(BaseGenerator):
    """Generator for categorical values with optional weights."""
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        choices = params.get("choices", [])
        if not choices:
            raise ColumnGenerationError(
                "No choices provided for categorical column",
                column_type="categorical",
                suggestion="Add 'choices' parameter with list of values"
            )
        
        weights = params.get("weights")
        if weights:
            if len(weights) != len(choices):
                raise ColumnGenerationError(
                    f"Weights length ({len(weights)}) doesn't match choices length ({len(choices)})",
                    column_type="categorical",
                    suggestion="Ensure weights and choices have the same length"
                )
            # Normalize weights
            weights = np.array(weights) / sum(weights)
        
        return np.random.choice(choices, size=size, p=weights)


class DateGenerator(BaseGenerator):
    """Generator for date values."""
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        import pandas as pd
        
        start = params.get("start", "2020-01-01")
        end = params.get("end", "2024-12-31")
        distribution = params.get("distribution", "uniform")
        
        start_ts = pd.Timestamp(start).value // 10**9
        end_ts = pd.Timestamp(end).value // 10**9
        
        if distribution == "uniform":
            timestamps = np.random.randint(start_ts, end_ts, size)
        elif distribution == "recent":
            # Bias towards recent dates (exponential decay)
            u = np.random.exponential(0.3, size)
            u = np.clip(u / u.max(), 0, 1)
            timestamps = (start_ts + (end_ts - start_ts) * u).astype(int)
        else:
            timestamps = np.random.randint(start_ts, end_ts, size)
        
        return pd.to_datetime(timestamps, unit='s').strftime('%Y-%m-%d').values


class TextGenerator(BaseGenerator):
    """Generator for text values using Faker or patterns."""
    
    def __init__(self):
        try:
            from faker import Faker
            self._faker = Faker()
        except ImportError:
            self._faker = None
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        text_type = params.get("text_type", params.get("distribution", "uuid"))
        
        if text_type == "uuid" or text_type == "text":
            import uuid
            return np.array([str(uuid.uuid4()) for _ in range(size)])
        
        if self._faker is None:
            # Fallback without faker
            return np.array([f"text_{i}" for i in range(size)])
        
        faker_methods = {
            "name": self._faker.name,
            "fake.name": self._faker.name,
            "email": self._faker.email,
            "fake.email": self._faker.email,
            "address": self._faker.address,
            "fake.address": self._faker.address,
            "company": self._faker.company,
            "fake.company": self._faker.company,
            "phone": self._faker.phone_number,
            "fake.phone": self._faker.phone_number,
            "city": self._faker.city,
            "country": self._faker.country,
            "job": self._faker.job,
            "sentence": self._faker.sentence,
            "paragraph": self._faker.paragraph,
        }
        
        method = faker_methods.get(text_type)
        if method:
            return np.array([method() for _ in range(size)])
        
        # Default to name
        return np.array([self._faker.name() for _ in range(size)])


class ForeignKeyGenerator(BaseGenerator):
    """Generator for foreign key references."""
    
    def __init__(self, parent_ids: Optional[np.ndarray] = None):
        self.parent_ids = parent_ids
    
    def set_parent_ids(self, parent_ids: np.ndarray) -> None:
        """Set the valid parent IDs for foreign key generation."""
        self.parent_ids = parent_ids
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        if self.parent_ids is None or len(self.parent_ids) == 0:
            raise ColumnGenerationError(
                "No parent IDs available for foreign key generation",
                column_type="foreign_key",
                suggestion="Ensure parent table is generated before child table"
            )
        
        return np.random.choice(self.parent_ids, size=size)


# ============ Generator Factory ============

class GeneratorFactory:
    """Factory for creating generators based on column type.
    
    Example:
        factory = GeneratorFactory()
        gen = factory.get_generator("int")
        values = gen.generate(1000, {"min": 1, "max": 100})
    """
    
    _generators: Dict[str, Type[BaseGenerator]] = {
        "int": IntegerGenerator,
        "integer": IntegerGenerator,
        "float": FloatGenerator,
        "double": FloatGenerator,
        "decimal": FloatGenerator,
        "boolean": BooleanGenerator,
        "bool": BooleanGenerator,
        "categorical": CategoricalGenerator,
        "category": CategoricalGenerator,
        "date": DateGenerator,
        "datetime": DateGenerator,
        "text": TextGenerator,
        "string": TextGenerator,
        "varchar": TextGenerator,
        "foreign_key": ForeignKeyGenerator,
        "fk": ForeignKeyGenerator,
    }
    
    _instances: Dict[str, BaseGenerator] = {}
    
    @classmethod
    def register(cls, column_type: str, generator_class: Type[BaseGenerator]) -> None:
        """Register a custom generator for a column type.
        
        Args:
            column_type: Type name (e.g., "custom_int")
            generator_class: Generator class to use
        """
        cls._generators[column_type.lower()] = generator_class
    
    @classmethod
    def get_generator(cls, column_type: str) -> BaseGenerator:
        """Get a generator instance for the given column type.
        
        Args:
            column_type: Column type (e.g., "int", "text", "date")
            
        Returns:
            Generator instance
            
        Raises:
            ColumnGenerationError: If column type is not supported
        """
        column_type = column_type.lower()
        
        if column_type not in cls._generators:
            raise ColumnGenerationError(
                f"Unsupported column type: {column_type}",
                column_type=column_type,
                suggestion=f"Supported types: {', '.join(cls._generators.keys())}"
            )
        
        # Get or create instance
        if column_type not in cls._instances:
            cls._instances[column_type] = cls._generators[column_type]()
        
        return cls._instances[column_type]
    
    @classmethod
    def create_foreign_key_generator(cls, parent_ids: np.ndarray) -> ForeignKeyGenerator:
        """Create a foreign key generator with parent IDs.
        
        Args:
            parent_ids: Array of valid parent IDs
            
        Returns:
            Configured ForeignKeyGenerator
        """
        gen = ForeignKeyGenerator(parent_ids)
        return gen


class ConditionalCategoricalGenerator(BaseGenerator):
    """Generator for categorical values that depend on another column.
    
    Use this for hierarchical data like state/country, department/role.
    
    Example:
        lookup = {
            "USA": ["California", "Texas", "New York"],
            "UK": ["England", "Scotland", "Wales"],
            "Germany": ["Bavaria", "Berlin", "Hamburg"],
        }
        gen = ConditionalCategoricalGenerator(lookup, "country")
        states = gen.generate(1000, {"parent_values": country_column})
    """
    
    def __init__(
        self, 
        lookup: Dict[str, List[str]], 
        parent_column: str,
        default_values: Optional[List[str]] = None
    ):
        """Initialize conditional generator.
        
        Args:
            lookup: Mapping from parent value to list of child values
            parent_column: Name of the parent column
            default_values: Values to use if parent not in lookup
        """
        self.lookup = lookup
        self.parent_column = parent_column
        self.default_values = default_values or list(lookup.values())[0] if lookup else ["Unknown"]
    
    def generate(self, size: int, params: Dict[str, Any]) -> np.ndarray:
        """Generate values conditioned on parent column.
        
        Args:
            size: Number of values to generate
            params: Must include 'parent_values' array
            
        Returns:
            Array of generated values
        """
        parent_values = params.get("parent_values")
        
        if parent_values is None:
            # No parent values, use uniform random from all possible values
            all_values = []
            for values in self.lookup.values():
                all_values.extend(values)
            if not all_values:
                all_values = self.default_values
            return np.random.choice(all_values, size=size)
        
        # Convert to array if needed
        parent_values = np.asarray(parent_values)
        
        if len(parent_values) != size:
            raise ColumnGenerationError(
                f"Parent values length ({len(parent_values)}) doesn't match size ({size})",
                column_type="conditional_categorical",
                suggestion="Ensure parent column is generated first"
            )
        
        # Generate conditional values
        result = np.empty(size, dtype=object)
        for i, parent in enumerate(parent_values):
            choices = self.lookup.get(str(parent), self.default_values)
            result[i] = np.random.choice(choices)
        
        return result


# ============ Built-in Lookup Tables ============

CONDITIONAL_LOOKUPS = {
    "country_to_state": {
        "USA": ["California", "Texas", "New York", "Florida", "Illinois", "Pennsylvania", "Ohio", "Georgia", "Michigan", "North Carolina"],
        "UK": ["England", "Scotland", "Wales", "Northern Ireland"],
        "Germany": ["Bavaria", "Berlin", "Hamburg", "Hesse", "North Rhine-Westphalia", "Baden-Württemberg"],
        "France": ["Île-de-France", "Provence", "Normandy", "Brittany", "Alsace"],
        "Canada": ["Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba"],
        "Australia": ["New South Wales", "Victoria", "Queensland", "Western Australia", "South Australia"],
        "India": ["Maharashtra", "Karnataka", "Tamil Nadu", "Delhi", "Gujarat", "Uttar Pradesh"],
        "Japan": ["Tokyo", "Osaka", "Kyoto", "Hokkaido", "Okinawa"],
    },
    "department_to_role": {
        "Engineering": ["Software Engineer", "Senior Engineer", "Staff Engineer", "Principal Engineer", "Engineering Manager"],
        "Product": ["Product Manager", "Senior PM", "Product Director", "VP Product", "Product Analyst"],
        "Design": ["UX Designer", "UI Designer", "Product Designer", "Design Lead", "Design Director"],
        "Sales": ["Sales Rep", "Account Executive", "Sales Manager", "Sales Director", "VP Sales"],
        "Marketing": ["Marketing Manager", "Content Strategist", "Growth Manager", "Marketing Director", "CMO"],
        "HR": ["HR Manager", "Recruiter", "HR Director", "People Partner", "VP People"],
        "Finance": ["Financial Analyst", "Accountant", "Controller", "Finance Director", "CFO"],
    },
    "category_to_subcategory": {
        "Electronics": ["Smartphones", "Laptops", "Tablets", "Accessories", "Wearables"],
        "Clothing": ["Men's Apparel", "Women's Apparel", "Kids", "Shoes", "Accessories"],
        "Home & Garden": ["Furniture", "Decor", "Kitchen", "Outdoor", "Bedding"],
        "Sports": ["Fitness", "Outdoor Sports", "Team Sports", "Water Sports", "Winter Sports"],
        "Books": ["Fiction", "Non-Fiction", "Academic", "Children's", "Comics"],
    },
    "industry_to_company_type": {
        "Technology": ["SaaS", "Consumer Tech", "Enterprise Software", "AI/ML", "Cybersecurity"],
        "Healthcare": ["Hospital", "Pharmaceutical", "Biotech", "Medical Device", "Health Insurance"],
        "Finance": ["Bank", "Investment Firm", "Insurance", "Fintech", "Credit Union"],
        "Retail": ["E-commerce", "Brick & Mortar", "Wholesale", "Specialty Retail", "Marketplace"],
        "Manufacturing": ["Automotive", "Electronics", "Consumer Goods", "Industrial", "Aerospace"],
    },
}


def create_conditional_generator(
    lookup_name: str,
    parent_column: str
) -> ConditionalCategoricalGenerator:
    """Create a conditional generator from built-in lookup tables.
    
    Args:
        lookup_name: Name of the lookup (e.g., "country_to_state")
        parent_column: Name of the parent column
        
    Returns:
        Configured ConditionalCategoricalGenerator
    """
    if lookup_name not in CONDITIONAL_LOOKUPS:
        available = ", ".join(CONDITIONAL_LOOKUPS.keys())
        raise ColumnGenerationError(
            f"Unknown lookup: {lookup_name}",
            column_type="conditional_categorical",
            suggestion=f"Available lookups: {available}"
        )
    
    return ConditionalCategoricalGenerator(
        lookup=CONDITIONAL_LOOKUPS[lookup_name],
        parent_column=parent_column
    )
