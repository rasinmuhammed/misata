"""
Caching utilities for Misata.

Provides LLM response caching using diskcache for performance optimization.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    import diskcache
    HAS_DISKCACHE = True
except ImportError:
    HAS_DISKCACHE = False


class LLMCache:
    """Cache for LLM responses to avoid repeated API calls.
    
    Uses diskcache for persistent storage with automatic expiration.
    Falls back to in-memory dict if diskcache is not installed.
    
    Example:
        cache = LLMCache()
        
        # Check cache first
        key = cache.make_key("groq", "llama-3.3", prompt)
        cached = cache.get(key)
        if cached:
            return cached
        
        # Make LLM call
        response = llm.generate(prompt)
        
        # Cache the result
        cache.set(key, response)
    """
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_size_mb: int = 100,
        expire_days: int = 7,
    ):
        """Initialize the cache.
        
        Args:
            cache_dir: Directory for cache storage (default: ~/.misata/cache)
            max_size_mb: Maximum cache size in MB
            expire_days: Days before cache entries expire
        """
        self.expire_seconds = expire_days * 24 * 60 * 60
        
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.misata/cache/llm")
        
        self.cache_dir = Path(cache_dir)
        
        if HAS_DISKCACHE:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache = diskcache.Cache(
                str(self.cache_dir),
                size_limit=max_size_mb * 1024 * 1024,
            )
        else:
            # Fallback to in-memory cache
            self._cache: Dict[str, Any] = {}
            self._memory_mode = True
    
    def make_key(
        self,
        provider: str,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        **kwargs: Any
    ) -> str:
        """Create a cache key from request parameters.
        
        Args:
            provider: LLM provider (groq, openai, etc.)
            model: Model name
            prompt: The prompt text
            temperature: Temperature setting
            **kwargs: Additional parameters to include in key
            
        Returns:
            Hash-based cache key
        """
        key_data = {
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            **kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]
    
    def get(self, key: str) -> Optional[Any]:
        """Get a cached value.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if HAS_DISKCACHE:
            return self._cache.get(key)
        else:
            return self._cache.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Store a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable for persistence)
        """
        if HAS_DISKCACHE:
            self._cache.set(key, value, expire=self.expire_seconds)
        else:
            self._cache[key] = value
    
    def delete(self, key: str) -> bool:
        """Delete a cached value.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        if HAS_DISKCACHE:
            return self._cache.delete(key)
        else:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cached values."""
        if HAS_DISKCACHE:
            self._cache.clear()
        else:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if HAS_DISKCACHE:
            return {
                "type": "diskcache",
                "directory": str(self.cache_dir),
                "size_bytes": self._cache.volume(),
                "count": len(self._cache),
            }
        else:
            return {
                "type": "memory",
                "count": len(self._cache),
            }
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
    
    def close(self) -> None:
        """Close the cache (required for diskcache)."""
        if HAS_DISKCACHE:
            self._cache.close()


class SmartValueCache:
    """Cache for SmartValueGenerator pools.
    
    Caches generated value pools by domain/context to avoid
    repeated LLM calls for the same domain.
    """
    
    def __init__(self, cache: Optional[LLMCache] = None):
        self._cache = cache or LLMCache(
            cache_dir=os.path.expanduser("~/.misata/cache/smart_values")
        )
    
    def get_pool(
        self,
        domain: str,
        context: Optional[str] = None,
        provider: str = "groq"
    ) -> Optional[list]:
        """Get cached value pool for a domain.
        
        Args:
            domain: Domain type (disease, prescription, etc.)
            context: Additional context
            provider: LLM provider used
            
        Returns:
            List of values or None if not cached
        """
        key = self._make_pool_key(domain, context, provider)
        return self._cache.get(key)
    
    def set_pool(
        self,
        domain: str,
        values: list,
        context: Optional[str] = None,
        provider: str = "groq"
    ) -> None:
        """Cache a value pool.
        
        Args:
            domain: Domain type
            values: List of generated values
            context: Additional context
            provider: LLM provider used
        """
        key = self._make_pool_key(domain, context, provider)
        self._cache.set(key, values)
    
    def _make_pool_key(
        self,
        domain: str,
        context: Optional[str],
        provider: str
    ) -> str:
        key_data = f"{provider}:{domain}:{context or ''}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:24]
    
    def clear(self) -> None:
        """Clear all cached pools."""
        self._cache.clear()


# Global cache instances
_llm_cache: Optional[LLMCache] = None
_smart_value_cache: Optional[SmartValueCache] = None


def get_llm_cache() -> LLMCache:
    """Get the global LLM cache instance."""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache()
    return _llm_cache


def get_smart_value_cache() -> SmartValueCache:
    """Get the global smart value cache instance."""
    global _smart_value_cache
    if _smart_value_cache is None:
        _smart_value_cache = SmartValueCache()
    return _smart_value_cache
