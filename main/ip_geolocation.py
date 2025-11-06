import requests
import json
import time
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Union, List
import sqlite3
from datetime import datetime, timedelta
import asyncio
import aiohttp
import ipaddress
from concurrent.futures import ThreadPoolExecutor

class IPGeolocation:
    def __init__(self, cache_file: str = "ip_cache.db", cache_duration_days: int = 30):
        """
        Initialize IP Geolocation service with free APIs and local caching
        
        Args:
            cache_file: SQLite database file for caching results
            cache_duration_days: How long to cache results (default 30 days)
        """
        self.cache_file = cache_file
        self.cache_duration = timedelta(days=cache_duration_days)
        
        # API endpoints (free services)
        self.primary_api = "http://ip-api.com/json/{}"  # 45,000 requests/hour
        self.fallback_api = "http://ipapi.co/{}/json/"  # 1,000 requests/day
    self.primary_api_batch = "http://ip-api.com/batch"  # up to 100 IPs per request
        
        # Rate limiting
        self.request_count = 0
        self.last_request_time = 0
        self.rate_limit_delay = 0.1  # 100ms between requests for ip-api.com
        
        # Initialize cache database
        self._init_cache()
        
        print("IP Geolocation initialized with free APIs, caching, and batch processing")
    
    def _init_cache(self):
        """Initialize SQLite cache database"""
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ip_cache (
                    ip TEXT PRIMARY KEY,
                    city TEXT,
                    country TEXT,
                    continent TEXT,
                    latitude REAL,
                    longitude REAL,
                    timezone TEXT,
                    postal_code TEXT,
                    subdivision TEXT,
                    source TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Warning: Could not initialize IP cache: {e}")
    
    def _is_public_ip(self, ip: str) -> bool:
        """Check if IP address is public (not private/reserved)"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            # Skip private, loopback, multicast, and reserved IP ranges
            return ip_obj.is_global and not (
                ip_obj.is_private or 
                ip_obj.is_loopback or 
                ip_obj.is_multicast or 
                ip_obj.is_reserved or
                ip_obj.is_link_local
            )
        except (ValueError, ipaddress.AddressValueError):
            return False  # Invalid IP format
    
    def _filter_public_ips(self, ips: List[str]) -> tuple[List[str], List[str]]:
        """Separate public IPs from private/invalid ones"""
        public_ips = []
        private_ips = []
        
        for ip in ips:
            if self._is_public_ip(ip):
                public_ips.append(ip)
            else:
                private_ips.append(ip)
        
        return public_ips, private_ips

    def _get_cached_location(self, ip: str) -> Optional[Dict[str, Optional[Union[str, float]]]]:
        """Get location from cache if available and not expired"""
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            # Check for cached result within duration
            cutoff_date = datetime.now() - self.cache_duration
            cursor.execute('''
                SELECT city, country, continent, latitude, longitude, 
                       timezone, postal_code, subdivision, source
                FROM ip_cache 
                WHERE ip = ? AND cached_at > ?
            ''', (ip, cutoff_date.isoformat()))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'city': result[0],
                    'country': result[1],
                    'continent': result[2],
                    'latitude': result[3],
                    'longitude': result[4],
                    'timezone': result[5],
                    'postal_code': result[6],
                    'subdivision': result[7],
                    'source': result[8] + ' (cached)'
                }
        except Exception as e:
            print(f"⚠️ Cache read error for {ip}: {e}")
        
        return None
    
    def _cache_location(self, ip: str, location_data: Dict, source: str):
        """Cache location data"""
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO ip_cache 
                (ip, city, country, continent, latitude, longitude, 
                 timezone, postal_code, subdivision, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ip, location_data.get('city'), location_data.get('country'),
                location_data.get('continent'), location_data.get('latitude'),
                location_data.get('longitude'), location_data.get('timezone'),
                location_data.get('postal_code'), location_data.get('subdivision'),
                source
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Cache write error for {ip}: {e}")
    
    def _rate_limit(self):
        """Implement rate limiting between API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = time.time()
    
    def _query_ip_api(self, ip: str) -> Dict[str, Optional[Union[str, float]]]:
        """Query ip-api.com (primary service)"""
        try:
            self._rate_limit()
            response = requests.get(self.primary_api.format(ip), timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if request was successful
                if data.get('status') == 'success':
                    return {
                        'city': data.get('city'),
                        'country': data.get('country'),
                        'continent': data.get('continent'),
                        'latitude': data.get('lat'),
                        'longitude': data.get('lon'),
                        'timezone': data.get('timezone'),
                        'postal_code': data.get('zip'),
                        'subdivision': data.get('regionName'),
                        'source': 'ip-api.com'
                    }
                elif data.get('status') == 'fail':
                    # Rate limit or quota exceeded
                    if 'quota' in data.get('message', '').lower():
                        raise Exception("Rate limit exceeded")
            
        except Exception as e:
            print(f"⚠️ ip-api.com failed for {ip}: {e}")
            raise
        
        return self._get_null_location('ip-api.com (failed)')
    
    def _query_ipapi_co(self, ip: str) -> Dict[str, Optional[Union[str, float]]]:
        """Query ipapi.co (fallback service)"""
        try:
            self._rate_limit()
            response = requests.get(self.fallback_api.format(ip), timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for error response
                if not data.get('error'):
                    return {
                        'city': data.get('city'),
                        'country': data.get('country_name'),
                        'continent': data.get('continent_code'),
                        'latitude': data.get('latitude'),
                        'longitude': data.get('longitude'),
                        'timezone': data.get('timezone'),
                        'postal_code': data.get('postal'),
                        'subdivision': data.get('region'),
                        'source': 'ipapi.co'
                    }
            
        except Exception as e:
            print(f"⚠️ ipapi.co failed for {ip}: {e}")
        
        return self._get_null_location('ipapi.co (failed)')
    
    def _get_null_location(self, source: str = 'unknown') -> Dict[str, Optional[Union[str, float]]]:
        """Return null location data"""
        return {
            'city': None,
            'country': None,
            'continent': None,
            'latitude': None,
            'longitude': None,
            'timezone': None,
            'postal_code': None,
            'subdivision': None,
            'source': source
        }
    
    def get_location(self, ip: str) -> Dict[str, Optional[Union[str, float]]]:
        """
        Get location for IP address with caching and fallback
        
        Args:
            ip: IP address to lookup
            
        Returns:
            Dictionary with location data
        """
        # First check cache
        cached_result = self._get_cached_location(ip)
        if cached_result:
            return cached_result
        
        # Try primary API (ip-api.com)
        try:
            location_data = self._query_ip_api(ip)
            if location_data.get('city') is not None:  # Successful lookup
                source = str(location_data.get('source', 'unknown'))
                self._cache_location(ip, location_data, source)
                return location_data
        except Exception as e:
            print(f"🔄 Primary API failed, trying fallback...")
        
        # Try fallback API (ipapi.co)
        try:
            location_data = self._query_ipapi_co(ip)
            if location_data.get('city') is not None:  # Successful lookup
                source = str(location_data.get('source', 'unknown'))
                self._cache_location(ip, location_data, source)
                return location_data
        except Exception as e:
            print(f"⚠️ Fallback API also failed for {ip}")
        
        # Return null data if both APIs failed
        null_result = self._get_null_location('API lookup failed')
        return null_result

    def _query_ip_api_batch(self, ips: List[str]) -> Dict[str, Dict[str, Optional[Union[str, float]]]]:
        """Batch query ip-api.com for up to 100 IPs per request.

        Returns a dict mapping ip -> location_data. Any failures will map to null location.
        """
        results: Dict[str, Dict[str, Optional[Union[str, float]]]] = {}
        if not ips:
            return results

        # ip-api batch supports fields selection via query param; keep payload light.
        fields = "status,message,query,city,country,lat,lon,timezone,zip,regionName"
        try:
            self._rate_limit()
            resp = requests.post(
                f"{self.primary_api_batch}?fields={fields}",
                json=ips,
                timeout=20,
            )
            if resp.status_code != 200:
                raise Exception(f"batch HTTP {resp.status_code}")
            data = resp.json()
            if not isinstance(data, list):
                raise Exception("unexpected batch response format")

            for item in data:
                ip = item.get("query")
                status = item.get("status")
                if ip is None:
                    continue
                if status == "success":
                    loc = {
                        'city': item.get('city'),
                        'country': item.get('country'),
                        'continent': None,  # not provided by ip-api free endpoint
                        'latitude': item.get('lat'),
                        'longitude': item.get('lon'),
                        'timezone': item.get('timezone'),
                        'postal_code': item.get('zip'),
                        'subdivision': item.get('regionName'),
                        'source': 'ip-api.com(batch)'
                    }
                    results[ip] = loc
                else:
                    # failed lookup for this IP
                    results[ip] = self._get_null_location('ip-api.com(batch failed)')
        except Exception as e:
            print(f"⚠️ ip-api.com batch failed: {e}")
            # On total batch failure, return empty dict to allow caller to fallback per-IP
            return {}

        return results
    
    def get_locations_batch_optimized(self, ips: List[str]) -> Dict[str, Dict[str, Optional[Union[str, float]]]]:
        """Optimized batch processing of multiple IPs with filtering and concurrent requests"""
        results = {}
        
        # Step 1: Filter out private/invalid IPs
        public_ips, private_ips = self._filter_public_ips(ips)
        
        if private_ips:
            print(f"Skipping {len(private_ips)} private/invalid IPs (no API calls needed)")
            # Add null results for private IPs
            for ip in private_ips:
                results[ip] = self._get_null_location('private/invalid IP')
        
        if not public_ips:
            print("No public IPs to process")
            return results
        
        print(f"Processing {len(public_ips)} public IP addresses...")
        
        # Step 2: Check cache for public IPs
        uncached_ips = []
        cached_count = 0
        
        for ip in public_ips:
            cached = self._get_cached_location(ip)
            if cached:
                results[ip] = cached
                cached_count += 1
            else:
                uncached_ips.append(ip)
        
        print(f"Cache: {cached_count} IPs found in cache, {len(uncached_ips)} need API calls")
        
        # Step 3: Process uncached IPs using ip-api batch endpoint first (fast path)
        if uncached_ips:
            batch_size = 100  # ip-api.com batch limit
            remaining_for_fallback: List[str] = []

            print(f"Processing {len(uncached_ips)} IPs via ip-api.com batch...")
            for i in range(0, len(uncached_ips), batch_size):
                chunk = uncached_ips[i:i+batch_size]
                batch_map = self._query_ip_api_batch(chunk)

                if batch_map:
                    # store successes and identify failures for fallback
                    for ip in chunk:
                        loc = batch_map.get(ip)
                        if loc and loc.get('city') is not None:
                            # cache success
                            try:
                                self._cache_location(ip, loc, str(loc.get('source', 'unknown')))
                            except Exception:
                                pass
                            results[ip] = loc
                        else:
                            remaining_for_fallback.append(ip)
                else:
                    # total batch failure for this chunk; push all to fallback
                    remaining_for_fallback.extend(chunk)
                # Gentle delay between batches
                time.sleep(0.2)

            # Step 4: Fallback for any unresolved IPs
            if remaining_for_fallback:
                if len(remaining_for_fallback) <= 5:
                    print(f"Fallback sequential for {len(remaining_for_fallback)} IPs...")
                    for ip in remaining_for_fallback:
                        results[ip] = self.get_location(ip)
                else:
                    print(f"Fallback concurrent for {len(remaining_for_fallback)} IPs...")
                    results.update(self._process_concurrent_batch(remaining_for_fallback))
        
        return results
    
    def _process_concurrent_batch(self, ips: List[str]) -> Dict[str, Dict[str, Optional[Union[str, float]]]]:
        """Process IPs concurrently with controlled rate limiting"""
        results = {}
        
        # Use ThreadPoolExecutor with limited workers to respect rate limits
        max_workers = min(5, len(ips))  # Max 5 concurrent requests
        
        def process_single_ip(ip):
            try:
                # Add small delay to respect rate limits
                time.sleep(0.2)  # 200ms delay between concurrent requests
                return ip, self.get_location(ip)
            except Exception as e:
                print(f"⚠️ Error processing {ip}: {e}")
                return ip, self._get_null_location(f'error: {e}')
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_ip = {executor.submit(process_single_ip, ip): ip for ip in ips}
            
            # Collect results
            completed = 0
            for future in future_to_ip:
                try:
                    ip, location_data = future.result(timeout=30)  # 30 second timeout
                    results[ip] = location_data
                    completed += 1
                    
                    if completed % 5 == 0:
                        print(f"📍 Completed {completed}/{len(ips)} concurrent lookups...")
                        
                except Exception as e:
                    ip = future_to_ip[future]
                    print(f"⚠️ Timeout/error for {ip}: {e}")
                    results[ip] = self._get_null_location(f'timeout: {e}')
        
        return results
    
    def process_dataframe(self, df: pd.DataFrame, ip_column: str) -> pd.DataFrame:
        """Process a dataframe with IP addresses and add geolocation columns - OPTIMIZED"""
        print(f"🔍 Processing geolocation for {len(df)} rows...")
        
        # Get unique IPs to avoid duplicate API calls
        unique_ips = df[ip_column].dropna().unique().tolist()
        print(f"📍 Found {len(unique_ips)} unique IP addresses")
        
        if not unique_ips:
            print("⚠️ No valid IP addresses found to process")
            return df
        
        # Use optimized batch processing
        start_time = time.time()
        location_results = self.get_locations_batch_optimized(unique_ips)
        processing_time = time.time() - start_time
        
        print(f"⚡ Batch processing completed in {processing_time:.2f} seconds")
        
        # Map results back to dataframe
        location_data = df[ip_column].map(location_results).apply(pd.Series)
        
        # Report statistics before renaming columns
        if 'source' in location_data.columns:
            successful_lookups = location_data['source'].notna().sum()
        else:
            successful_lookups = 0
        
        # Add prefix to avoid column name conflicts
        location_columns = {col: f'geo_{col}' for col in location_data.columns}
        location_data = location_data.rename(columns=location_columns)
        
        # Combine with original dataframe
        result_df = pd.concat([df, location_data], axis=1)
        
        print(f"✅ Geolocation complete: {successful_lookups}/{len(df)} successful lookups")
        
        return result_df
    
    def test_performance(self, test_ips: Optional[List[str]] = None) -> Dict[str, Dict[str, Optional[Union[str, float]]]]:
        """Test performance improvements with sample IPs"""
        if test_ips is None:
            # Sample test IPs (mix of public and private)
            test_ips = [
                '8.8.8.8',          # Google DNS (public)
                '1.1.1.1',          # Cloudflare DNS (public) 
                '192.168.1.1',      # Private IP (should be skipped)
                '10.0.0.1',         # Private IP (should be skipped)
                '208.67.222.222',   # OpenDNS (public)
                '127.0.0.1',        # Loopback (should be skipped)
                '134.195.196.26'    # Another public IP
            ]
        
        print(f"🧪 Testing geolocation performance with {len(test_ips)} IPs...")
        
        start_time = time.time()
        results = self.get_locations_batch_optimized(test_ips)
        end_time = time.time()
        
        print(f"⚡ Performance test completed in {end_time - start_time:.2f} seconds")
        print(f"📊 Results: {len(results)} IPs processed")
        
        # Show breakdown
        public_count = len([ip for ip in test_ips if self._is_public_ip(ip)])
        private_count = len(test_ips) - public_count
        
        print(f"   • {public_count} public IPs (required API calls)")
        print(f"   • {private_count} private/invalid IPs (skipped)")
        
        return results

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM ip_cache')
            total_cached = cursor.fetchone()[0]
            
            cutoff_date = datetime.now() - self.cache_duration
            cursor.execute('SELECT COUNT(*) FROM ip_cache WHERE cached_at > ?', 
                          (cutoff_date.isoformat(),))
            fresh_cached = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_cached': total_cached,
                'fresh_cached': fresh_cached,
                'expired_cached': total_cached - fresh_cached
            }
        except Exception:
            return {'total_cached': 0, 'fresh_cached': 0, 'expired_cached': 0}
    
    def clear_cache(self, older_than_days: Optional[int] = None):
        """Clear cache entries"""
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            if older_than_days:
                cutoff_date = datetime.now() - timedelta(days=older_than_days)
                cursor.execute('DELETE FROM ip_cache WHERE cached_at < ?', 
                              (cutoff_date.isoformat(),))
                print(f"🗑️ Cleared cache entries older than {older_than_days} days")
            else:
                cursor.execute('DELETE FROM ip_cache')
                print("🗑️ Cleared all cache entries")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Error clearing cache: {e}")