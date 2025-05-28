"""
FirecrawlApp Module

This module provides a class `FirecrawlApp` for interacting with the Firecrawl API.
It includes methods to scrape URLs, perform searches, initiate and monitor crawl jobs,
and check the status of these jobs. The module uses requests for HTTP communication
and handles retries for certain HTTP status codes.

Classes:
    - FirecrawlApp: Main class for interacting with the Firecrawl API.
"""
import logging
import os
import time
from typing import Any, Dict, Optional, List, Union, Callable, Literal, TypeVar, Generic
import json
from datetime import datetime
import re
import requests
import pydantic
import websockets
import aiohttp
import asyncio
from pydantic import Field
from .utils import parse_scrape_options, ensure_schema_dict, scrape_formats_transform, scrape_formats_response_transform, change_tracking_response_transform
from .types import LocationConfig, WebhookConfig, ChangeTrackingOptions, ScrapeOptions, ScrapeResponse, SearchResponse, CrawlStatusResponse, WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction, JsonConfig, CrawlResponse, CrawlErrorsResponse, CrawlParams, MapParams, MapResponse, AgentOptions, BatchScrapeStatusResponse, BatchScrapeResponse, ExtractResponse, ScrapeParams, SearchParams

def get_version():
  try:
      from pathlib import Path
      package_path = os.path.dirname(__file__)
      version_file = Path(os.path.join(package_path, '__init__.py')).read_text()
      version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
      if version_match:
          return version_match.group(1).strip()
  except Exception:
      print("Failed to get version from __init__.py")
      return None

version = get_version()

logger : logging.Logger = logging.getLogger("firecrawl")

class FirecrawlApp:
    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None) -> None:
        """
        Initialize the FirecrawlApp instance with API key, API URL.

        Args:
            api_key (Optional[str]): API key for authenticating with the Firecrawl API.
            api_url (Optional[str]): Base URL for the Firecrawl API.
        """
        self.api_key = api_key or os.getenv('FIRECRAWL_API_KEY')
        self.api_url = api_url or os.getenv('FIRECRAWL_API_URL', 'https://api.firecrawl.dev')
        
        # Only require API key when using cloud service
        if 'api.firecrawl.dev' in self.api_url and self.api_key is None:
            logger.warning("No API key provided for cloud service")
            raise ValueError('No API key provided')
            
        logger.debug(f"Initialized FirecrawlApp with API URL: {self.api_url}")

    def scrape_url(
            self,
            url: str,
            *,
            formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json", "change_tracking"]]] = None,
            include_tags: Optional[List[str]] = None,
            exclude_tags: Optional[List[str]] = None,
            only_main_content: Optional[bool] = None,
            wait_for: Optional[int] = None,
            timeout: Optional[int] = None,
            location: Optional[LocationConfig] = None,
            mobile: Optional[bool] = None,
            skip_tls_verification: Optional[bool] = None,
            remove_base64_images: Optional[bool] = None,
            block_ads: Optional[bool] = None,
            proxy: Optional[Literal["basic", "stealth"]] = None,
            extract: Optional[JsonConfig] = None,
            json_options: Optional[JsonConfig] = None,
            actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
            change_tracking_options: Optional[ChangeTrackingOptions] = None,
            **kwargs) -> ScrapeResponse[Any]:
        """
        Scrape and extract content from a URL.

        Args:
          url (str): Target URL to scrape
          formats (Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json", "change_tracking"]]]): Content types to retrieve (markdown/html/etc)
          include_tags (Optional[List[str]]): HTML tags to include
          exclude_tags (Optional[List[str]]): HTML tags to exclude
          only_main_content (Optional[bool]): Extract main content only
          wait_for (Optional[int]): Wait for a specific element to appear
          timeout (Optional[int]): Request timeout (ms)
          location (Optional[LocationConfig]): Location configuration
          mobile (Optional[bool]): Use mobile user agent
          skip_tls_verification (Optional[bool]): Skip TLS verification
          remove_base64_images (Optional[bool]): Remove base64 images
          block_ads (Optional[bool]): Block ads
          proxy (Optional[Literal["basic", "stealth"]]): Proxy type (basic/stealth)
          extract (Optional[JsonConfig]): Content extraction settings
          json_options (Optional[JsonConfig]): JSON extraction settings
          actions (Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]]): Actions to perform
          change_tracking_options (Optional[ChangeTrackingOptions]): Change tracking settings


        Returns:
          ScrapeResponse with:
          * Requested content formats
          * Page metadata
          * Extraction results
          * Success/error status

        Raises:
          Exception: If scraping fails
        """
        headers = self._prepare_headers()

        # Build scrape parameters
        scrape_params = {
            'url': url,
            'origin': f"python-sdk@{version}"
        }

        scrape_params.update(parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            change_tracking_options=change_tracking_options
        ))

        # Make request
        response = requests.post(
            f'{self.api_url}/v1/scrape',
            headers=headers,
            json=scrape_params,
            timeout=(timeout + 5000 if timeout else None)
        )

        if response.status_code == 200:
            try:
                response_json = response.json()
                if response_json.get('success') and 'data' in response_json:
                    data = response_json['data']
                    data = scrape_formats_response_transform(data)
                    if 'change_tracking' in data:
                        data['change_tracking'] = change_tracking_response_transform(data['change_tracking'])
                    return ScrapeResponse(**data)
                elif "error" in response_json:
                    raise Exception(f'Failed to scrape URL. Error: {response_json["error"]}')
                else:
                    raise Exception(f'Failed to scrape URL. Error: {response_json}')
            except ValueError:
                raise Exception('Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'scrape URL')

    def search(
            self,
            query: str,
            *,
            limit: Optional[int] = None,
            tbs: Optional[str] = None,
            filter: Optional[str] = None,
            lang: Optional[str] = None,
            country: Optional[str] = None,
            location: Optional[str] = None,
            timeout: Optional[int] = None,
            scrape_options: Optional[ScrapeOptions] = None,
            **kwargs) -> SearchResponse:
        """
        Search for content using Firecrawl.

        Args:
            query (str): Search query string
            limit (Optional[int]): Max results (default: 5)
            tbs (Optional[str]): Time filter (e.g. "qdr:d")
            filter (Optional[str]): Custom result filter
            lang (Optional[str]): Language code (default: "en")
            country (Optional[str]): Country code (default: "us") 
            location (Optional[str]): Geo-targeting
            timeout (Optional[int]): Request timeout in milliseconds
            scrape_options (Optional[ScrapeOptions]): Result scraping configuration
            **kwargs: Additional keyword arguments for future compatibility

        Returns:
            SearchResponse: Response containing:
                * success (bool): Whether request succeeded
                * data (List[FirecrawlDocument]): Search results
                * warning (Optional[str]): Warning message if any
                * error (Optional[str]): Error message if any

        Raises:
            Exception: If search fails or response cannot be parsed
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "search")

        # Build search parameters
        search_params = {}

        # Add individual parameters
        if limit is not None:
            search_params['limit'] = limit
        if tbs is not None:
            search_params['tbs'] = tbs
        if filter is not None:
            search_params['filter'] = filter
        if lang is not None:
            search_params['lang'] = lang
        if country is not None:
            search_params['country'] = country
        if location is not None:
            search_params['location'] = location
        if timeout is not None:
            search_params['timeout'] = timeout
        if scrape_options is not None:
            search_params['scrapeOptions'] = scrape_options.model_dump(exclude_none=True)
        
        # Add any additional kwargs
        search_params.update(kwargs)

        # Create final params object
        final_params = SearchParams(query=query, **search_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        response = requests.post(
            f"{self.api_url}/v1/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=params_dict
        )

        if response.status_code == 200:
            try:
                response_json = response.json()
                if response_json.get('success') and 'data' in response_json:
                    return SearchResponse(**response_json)
                elif "error" in response_json:
                    raise Exception(f'Search failed. Error: {response_json["error"]}')
                else:
                    raise Exception(f'Search failed. Error: {response_json}')
            except ValueError:
                raise Exception('Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'search')

    def crawl_url(
        self,
        url: str,
        *,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_discovery_depth: Optional[int] = None,
        limit: Optional[int] = None,
        allow_backward_links: Optional[bool] = None,
        allow_external_links: Optional[bool] = None,
        ignore_sitemap: Optional[bool] = None,
        scrape_options: Optional[ScrapeOptions] = None,
        webhook: Optional[Union[str, WebhookConfig]] = None,
        deduplicate_similar_urls: Optional[bool] = None,
        ignore_query_parameters: Optional[bool] = None,
        regex_on_full_url: Optional[bool] = None,
        delay: Optional[int] = None,
        poll_interval: Optional[int] = 2,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> CrawlStatusResponse:
        """
        Crawl a website starting from a URL.

        Args:
            url (str): Target URL to start crawling from
            include_paths (Optional[List[str]]): Patterns of URLs to include
            exclude_paths (Optional[List[str]]): Patterns of URLs to exclude
            max_depth (Optional[int]): Maximum crawl depth
            max_discovery_depth (Optional[int]): Maximum depth for finding new URLs
            limit (Optional[int]): Maximum pages to crawl
            allow_backward_links (Optional[bool]): Follow parent directory links
            allow_external_links (Optional[bool]): Follow external domain links
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            scrape_options (Optional[ScrapeOptions]): Page scraping configuration
            webhook (Optional[Union[str, WebhookConfig]]): Notification webhook settings
            deduplicate_similar_urls (Optional[bool]): Remove similar URLs
            ignore_query_parameters (Optional[bool]): Ignore URL parameters
            regex_on_full_url (Optional[bool]): Apply regex to full URLs
            delay (Optional[int]): Delay in seconds between scrapes
            poll_interval (Optional[int]): Seconds between status checks (default: 2)
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlStatusResponse with:
            * Crawling status and progress
            * Crawled page contents
            * Success/error information

        Raises:
            Exception: If crawl fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "crawl_url")

        crawl_params = {}

        # Add individual parameters
        if include_paths is not None:
            crawl_params['includePaths'] = include_paths
        if exclude_paths is not None:
            crawl_params['excludePaths'] = exclude_paths
        if max_depth is not None:
            crawl_params['maxDepth'] = max_depth
        if max_discovery_depth is not None:
            crawl_params['maxDiscoveryDepth'] = max_discovery_depth
        if limit is not None:
            crawl_params['limit'] = limit
        if allow_backward_links is not None:
            crawl_params['allowBackwardLinks'] = allow_backward_links
        if allow_external_links is not None:
            crawl_params['allowExternalLinks'] = allow_external_links
        if ignore_sitemap is not None:
            crawl_params['ignoreSitemap'] = ignore_sitemap
        if scrape_options is not None:
            crawl_params['scrapeOptions'] = parse_scrape_options(scrape_options)
        if webhook is not None:
            crawl_params['webhook'] = webhook
        if deduplicate_similar_urls is not None:
            crawl_params['deduplicateSimilarURLs'] = deduplicate_similar_urls
        if ignore_query_parameters is not None:
            crawl_params['ignoreQueryParameters'] = ignore_query_parameters
        if regex_on_full_url is not None:
            crawl_params['regexOnFullURL'] = regex_on_full_url
        if delay is not None:
            crawl_params['delay'] = delay

        # Add any additional kwargs
        crawl_params.update(kwargs)

        # Create final params object
        final_params = CrawlParams(**crawl_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = self._post_request(f'{self.api_url}/v1/crawl', params_dict, headers)

        if response.status_code == 200:
            try:
                id = response.json().get('id')
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            return self._monitor_job_status(id, headers, poll_interval)
        else:
            self._handle_error(response, 'start crawl job')

    def async_crawl_url(
        self,
        url: str,
        *,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_discovery_depth: Optional[int] = None,
        limit: Optional[int] = None,
        allow_backward_links: Optional[bool] = None,
        allow_external_links: Optional[bool] = None,
        ignore_sitemap: Optional[bool] = None,
        scrape_options: Optional[ScrapeOptions] = None,
        webhook: Optional[Union[str, WebhookConfig]] = None,
        deduplicate_similar_urls: Optional[bool] = None,
        ignore_query_parameters: Optional[bool] = None,
        regex_on_full_url: Optional[bool] = None,
        delay: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> CrawlResponse:
        """
        Start an asynchronous crawl job.

        Args:
            url (str): Target URL to start crawling from
            include_paths (Optional[List[str]]): Patterns of URLs to include
            exclude_paths (Optional[List[str]]): Patterns of URLs to exclude
            max_depth (Optional[int]): Maximum crawl depth
            max_discovery_depth (Optional[int]): Maximum depth for finding new URLs
            limit (Optional[int]): Maximum pages to crawl
            allow_backward_links (Optional[bool]): Follow parent directory links
            allow_external_links (Optional[bool]): Follow external domain links
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            scrape_options (Optional[ScrapeOptions]): Page scraping configuration
            webhook (Optional[Union[str, WebhookConfig]]): Notification webhook settings
            deduplicate_similar_urls (Optional[bool]): Remove similar URLs
            ignore_query_parameters (Optional[bool]): Ignore URL parameters
            regex_on_full_url (Optional[bool]): Apply regex to full URLs
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlResponse with:
            * success - Whether crawl started successfully
            * id - Unique identifier for the crawl job
            * url - Status check URL for the crawl
            * error - Error message if start failed

        Raises:
            Exception: If crawl initiation fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "async_crawl_url")

        crawl_params = {}

        # Add individual parameters
        if include_paths is not None:
            crawl_params['includePaths'] = include_paths
        if exclude_paths is not None:
            crawl_params['excludePaths'] = exclude_paths
        if max_depth is not None:
            crawl_params['maxDepth'] = max_depth
        if max_discovery_depth is not None:
            crawl_params['maxDiscoveryDepth'] = max_discovery_depth
        if limit is not None:
            crawl_params['limit'] = limit
        if allow_backward_links is not None:
            crawl_params['allowBackwardLinks'] = allow_backward_links
        if allow_external_links is not None:
            crawl_params['allowExternalLinks'] = allow_external_links
        if ignore_sitemap is not None:
            crawl_params['ignoreSitemap'] = ignore_sitemap
        if scrape_options is not None:
            crawl_params['scrapeOptions'] = scrape_options.model_dump(exclude_none=True)
        if webhook is not None:
            crawl_params['webhook'] = webhook
        if deduplicate_similar_urls is not None:
            crawl_params['deduplicateSimilarURLs'] = deduplicate_similar_urls
        if ignore_query_parameters is not None:
            crawl_params['ignoreQueryParameters'] = ignore_query_parameters
        if regex_on_full_url is not None:
            crawl_params['regexOnFullURL'] = regex_on_full_url
        if delay is not None:
            crawl_params['delay'] = delay

        # Add any additional kwargs
        crawl_params.update(kwargs)

        # Create final params object
        final_params = CrawlParams(**crawl_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = self._post_request(f'{self.api_url}/v1/crawl', params_dict, headers)

        if response.status_code == 200:
            try:
                return CrawlResponse(**response.json())
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'start crawl job')

    def check_crawl_status(self, id: str) -> CrawlStatusResponse:
        """
        Check the status and results of a crawl job.

        Args:
            id: Unique identifier for the crawl job

        Returns:
            CrawlStatusResponse containing:

            Status Information:
            * status - Current state (scraping/completed/failed/cancelled)
            * completed - Number of pages crawled
            * total - Total pages to crawl
            * creditsUsed - API credits consumed
            * expiresAt - Data expiration timestamp
            
            Results:
            * data - List of crawled documents
            * next - URL for next page of results (if paginated)
            * success - Whether status check succeeded
            * error - Error message if failed

        Raises:
            Exception: If status check fails
        """
        endpoint = f'/v1/crawl/{id}'

        headers = self._prepare_headers()
        response = self._get_request(f'{self.api_url}{endpoint}', headers)
        if response.status_code == 200:
            try:
                status_data = response.json()
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            if status_data['status'] == 'completed':
                if 'data' in status_data:
                    data = status_data['data']
                    while 'next' in status_data:
                        if len(status_data['data']) == 0:
                            break
                        next_url = status_data.get('next')
                        if not next_url:
                            logger.warning("Expected 'next' URL is missing.")
                            break
                        try:
                            status_response = self._get_request(next_url, headers)
                            if status_response.status_code != 200:
                                logger.error(f"Failed to fetch next page: {status_response.status_code}")
                                break
                            try:
                                next_data = status_response.json()
                            except:
                                raise Exception(f'Failed to parse Firecrawl response as JSON.')
                            data.extend(next_data.get('data', []))
                            status_data = next_data
                        except Exception as e:
                            logger.error(f"Error during pagination request: {e}")
                            break
                    status_data['data'] = data

            response = {
                'status': status_data.get('status'),
                'total': status_data.get('total'),
                'completed': status_data.get('completed'),
                'credits_used': status_data.get('creditsUsed'),
                'expires_at': status_data.get('expiresAt'),
                'data': data,
                'next': status_data.get('next'),
                'error': status_data.get('error')
            }

            if 'error' in status_data:
                response['error'] = status_data['error']

            if 'next' in status_data:
                response['next'] = status_data['next']

            return CrawlStatusResponse(**response)
        else:
            self._handle_error(response, 'check crawl status')
    
    def check_crawl_errors(self, id: str) -> CrawlErrorsResponse:
        """
        Returns information about crawl errors.

        Args:
            id (str): The ID of the crawl job

        Returns:
            CrawlErrorsResponse containing:
            * errors (List[Dict[str, str]]): List of errors with fields:
                - id (str): Error ID
                - timestamp (str): When the error occurred
                - url (str): URL that caused the error
                - error (str): Error message
            * robotsBlocked (List[str]): List of URLs blocked by robots.txt

        Raises:
            Exception: If error check fails
        """
        headers = self._prepare_headers()
        response = self._get_request(f'{self.api_url}/v1/crawl/{id}/errors', headers)
        if response.status_code == 200:
            try:
                return CrawlErrorsResponse(**response.json())
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, "check crawl errors")
    
    def cancel_crawl(self, id: str) -> Dict[str, Any]:
        """
        Cancel an asynchronous crawl job.

        Args:
            id (str): The ID of the crawl job to cancel

        Returns:
            Dict[str, Any] containing:
            * success (bool): Whether cancellation was successful
            * error (str, optional): Error message if cancellation failed

        Raises:
            Exception: If cancellation fails
        """
        headers = self._prepare_headers()
        response = self._delete_request(f'{self.api_url}/v1/crawl/{id}', headers)
        if response.status_code == 200:
            try:
                return response.json()
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, "cancel crawl job")

    def crawl_url_and_watch(
            self,
            url: str,
            *,
            include_paths: Optional[List[str]] = None,
            exclude_paths: Optional[List[str]] = None,
            max_depth: Optional[int] = None,
            max_discovery_depth: Optional[int] = None,
            limit: Optional[int] = None,
            allow_backward_links: Optional[bool] = None,
            allow_external_links: Optional[bool] = None,
            ignore_sitemap: Optional[bool] = None,
            scrape_options: Optional[ScrapeOptions] = None,
            webhook: Optional[Union[str, WebhookConfig]] = None,
            deduplicate_similar_urls: Optional[bool] = None,
            ignore_query_parameters: Optional[bool] = None,
            regex_on_full_url: Optional[bool] = None,
            idempotency_key: Optional[str] = None,
            **kwargs
    ) -> 'CrawlWatcher':
        """
        Initiate a crawl job and return a CrawlWatcher to monitor the job via WebSocket.

        Args:
            url (str): Target URL to start crawling from
            include_paths (Optional[List[str]]): Patterns of URLs to include
            exclude_paths (Optional[List[str]]): Patterns of URLs to exclude
            max_depth (Optional[int]): Maximum crawl depth
            max_discovery_depth (Optional[int]): Maximum depth for finding new URLs
            limit (Optional[int]): Maximum pages to crawl
            allow_backward_links (Optional[bool]): Follow parent directory links
            allow_external_links (Optional[bool]): Follow external domain links
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            scrape_options (Optional[ScrapeOptions]): Page scraping configuration
            webhook (Optional[Union[str, WebhookConfig]]): Notification webhook settings
            deduplicate_similar_urls (Optional[bool]): Remove similar URLs
            ignore_query_parameters (Optional[bool]): Ignore URL parameters
            regex_on_full_url (Optional[bool]): Apply regex to full URLs
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlWatcher: An instance to monitor the crawl job via WebSocket

        Raises:
            Exception: If crawl job fails to start
        """
        crawl_response = self.async_crawl_url(
            url,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            max_depth=max_depth,
            max_discovery_depth=max_discovery_depth,
            limit=limit,
            allow_backward_links=allow_backward_links,
            allow_external_links=allow_external_links,
            ignore_sitemap=ignore_sitemap,
            scrape_options=scrape_options,
            webhook=webhook,
            deduplicate_similar_urls=deduplicate_similar_urls,
            ignore_query_parameters=ignore_query_parameters,
            regex_on_full_url=regex_on_full_url,
            idempotency_key=idempotency_key,
            **kwargs
        )
        if crawl_response.success and crawl_response.id:
            return CrawlWatcher(crawl_response.id, self)
        else:
            raise Exception("Crawl job failed to start")

    def map_url(
            self,
            url: str,
            *,
            search: Optional[str] = None,
            ignore_sitemap: Optional[bool] = None,
            include_subdomains: Optional[bool] = None,
            sitemap_only: Optional[bool] = None,
            limit: Optional[int] = None,
            timeout: Optional[int] = None,
            **kwargs) -> MapResponse:
        """
        Map and discover links from a URL.

        Args:
            url (str): Target URL to map
            search (Optional[str]): Filter pattern for URLs
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            include_subdomains (Optional[bool]): Include subdomain links
            sitemap_only (Optional[bool]): Only use sitemap.xml
            limit (Optional[int]): Maximum URLs to return
            timeout (Optional[int]): Request timeout in milliseconds
            **kwargs: Additional parameters to pass to the API

        Returns:
            MapResponse: Response containing:
                * success (bool): Whether request succeeded
                * links (List[str]): Discovered URLs
                * error (Optional[str]): Error message if any

        Raises:
            Exception: If mapping fails or response cannot be parsed
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "map_url")

        # Build map parameters
        map_params = {}

        # Add individual parameters
        if search is not None:
            map_params['search'] = search
        if ignore_sitemap is not None:
            map_params['ignoreSitemap'] = ignore_sitemap
        if include_subdomains is not None:
            map_params['includeSubdomains'] = include_subdomains
        if sitemap_only is not None:
            map_params['sitemapOnly'] = sitemap_only
        if limit is not None:
            map_params['limit'] = limit
        if timeout is not None:
            map_params['timeout'] = timeout

        # Add any additional kwargs
        map_params.update(kwargs)

        # Create final params object
        final_params = MapParams(**map_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        response = requests.post(
            f"{self.api_url}/v1/map",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=params_dict
        )

        if response.status_code == 200:
            try:
                response_json = response.json()
                if response_json.get('success') and 'links' in response_json:
                    return MapResponse(**response_json)
                elif "error" in response_json:
                    raise Exception(f'Map failed. Error: {response_json["error"]}')
                else:
                    raise Exception(f'Map failed. Error: {response_json}')
            except ValueError:
                raise Exception('Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'map')

    def batch_scrape_urls(
        self,
        urls: List[str],
        *,
        formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json"]]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        only_main_content: Optional[bool] = None,
        wait_for: Optional[int] = None,
        timeout: Optional[int] = None,
        location: Optional[LocationConfig] = None,
        mobile: Optional[bool] = None,
        skip_tls_verification: Optional[bool] = None,
        remove_base64_images: Optional[bool] = None,
        block_ads: Optional[bool] = None,
        proxy: Optional[Literal["basic", "stealth"]] = None,
        extract: Optional[JsonConfig] = None,
        json_options: Optional[JsonConfig] = None,
        actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
        agent: Optional[AgentOptions] = None,
        poll_interval: Optional[int] = 2,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> BatchScrapeStatusResponse:
        """
        Batch scrape multiple URLs and monitor until completion.

        Args:
            urls (List[str]): URLs to scrape
            formats (Optional[List[Literal]]): Content formats to retrieve
            headers (Optional[Dict[str, str]]): Custom HTTP headers
            include_tags (Optional[List[str]]): HTML tags to include
            exclude_tags (Optional[List[str]]): HTML tags to exclude
            only_main_content (Optional[bool]): Extract main content only
            wait_for (Optional[int]): Wait time in milliseconds
            timeout (Optional[int]): Request timeout in milliseconds
            location (Optional[LocationConfig]): Location configuration
            mobile (Optional[bool]): Use mobile user agent
            skip_tls_verification (Optional[bool]): Skip TLS verification
            remove_base64_images (Optional[bool]): Remove base64 encoded images
            block_ads (Optional[bool]): Block advertisements
            proxy (Optional[Literal]): Proxy type to use
            extract (Optional[JsonConfig]): Content extraction config
            json_options (Optional[JsonConfig]): JSON extraction config
            actions (Optional[List[Union]]): Actions to perform
            agent (Optional[AgentOptions]): Agent configuration
            poll_interval (Optional[int]): Seconds between status checks (default: 2)
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            BatchScrapeStatusResponse with:
            * Scraping status and progress
            * Scraped content for each URL
            * Success/error information

        Raises:
            Exception: If batch scrape fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "batch_scrape_urls")

        scrape_params = parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            agent=agent,
            **kwargs
        )

        # Create final params object
        scrape_params['urls'] = urls
        if idempotency_key:
            scrape_params['idempotencyKey'] = idempotency_key
        scrape_params['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = self._post_request(f'{self.api_url}/v1/batch/scrape', scrape_params, headers)

        if response.status_code == 200:
            try:
                id = response.json().get('id')
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            return self.check_batch_scrape_status(id, poll_interval=poll_interval)
        else:
            self._handle_error(response, 'start batch scrape job')

    def async_batch_scrape_urls(
        self,
        urls: List[str],
        *,
        formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json"]]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        only_main_content: Optional[bool] = None,
        wait_for: Optional[int] = None,
        timeout: Optional[int] = None,
        location: Optional[LocationConfig] = None,
        mobile: Optional[bool] = None,
        skip_tls_verification: Optional[bool] = None,
        remove_base64_images: Optional[bool] = None,
        block_ads: Optional[bool] = None,
        proxy: Optional[Literal["basic", "stealth"]] = None,
        extract: Optional[JsonConfig] = None,
        json_options: Optional[JsonConfig] = None,
        actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
        agent: Optional[AgentOptions] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> BatchScrapeResponse:
        """
        Initiate a batch scrape job asynchronously.

        Args:
            urls (List[str]): URLs to scrape
            formats (Optional[List[Literal]]): Content formats to retrieve
            headers (Optional[Dict[str, str]]): Custom HTTP headers
            include_tags (Optional[List[str]]): HTML tags to include
            exclude_tags (Optional[List[str]]): HTML tags to exclude
            only_main_content (Optional[bool]): Extract main content only
            wait_for (Optional[int]): Wait time in milliseconds
            timeout (Optional[int]): Request timeout in milliseconds
            location (Optional[LocationConfig]): Location configuration
            mobile (Optional[bool]): Use mobile user agent
            skip_tls_verification (Optional[bool]): Skip TLS verification
            remove_base64_images (Optional[bool]): Remove base64 encoded images
            block_ads (Optional[bool]): Block advertisements
            proxy (Optional[Literal]): Proxy type to use
            extract (Optional[JsonConfig]): Content extraction config
            json_options (Optional[JsonConfig]): JSON extraction config
            actions (Optional[List[Union]]): Actions to perform
            agent (Optional[AgentOptions]): Agent configuration
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            BatchScrapeResponse with:
            * success - Whether job started successfully
            * id - Unique identifier for the job
            * url - Status check URL
            * error - Error message if start failed

        Raises:
            Exception: If job initiation fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "async_batch_scrape_urls")

        scrape_params = parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            agent=agent,
            **kwargs
        )
  
        scrape_params['urls'] = urls
        scrape_params['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = self._post_request(f'{self.api_url}/v1/batch/scrape', scrape_params, headers)

        if response.status_code == 200:
            try:
                return BatchScrapeResponse(**response.json())
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'start batch scrape job')
    
    def batch_scrape_urls_and_watch(
        self,
        urls: List[str],
        *,
        formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json"]]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        only_main_content: Optional[bool] = None,
        wait_for: Optional[int] = None,
        timeout: Optional[int] = None,
        location: Optional[LocationConfig] = None,
        mobile: Optional[bool] = None,
        skip_tls_verification: Optional[bool] = None,
        remove_base64_images: Optional[bool] = None,
        block_ads: Optional[bool] = None,
        proxy: Optional[Literal["basic", "stealth"]] = None,
        extract: Optional[JsonConfig] = None,
        json_options: Optional[JsonConfig] = None,
        actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
        agent: Optional[AgentOptions] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> 'CrawlWatcher':
        """
        Initiate a batch scrape job and return a CrawlWatcher to monitor the job via WebSocket.

        Args:
            urls (List[str]): URLs to scrape
            formats (Optional[List[Literal]]): Content formats to retrieve
            headers (Optional[Dict[str, str]]): Custom HTTP headers
            include_tags (Optional[List[str]]): HTML tags to include
            exclude_tags (Optional[List[str]]): HTML tags to exclude
            only_main_content (Optional[bool]): Extract main content only
            wait_for (Optional[int]): Wait time in milliseconds
            timeout (Optional[int]): Request timeout in milliseconds
            location (Optional[LocationConfig]): Location configuration
            mobile (Optional[bool]): Use mobile user agent
            skip_tls_verification (Optional[bool]): Skip TLS verification
            remove_base64_images (Optional[bool]): Remove base64 encoded images
            block_ads (Optional[bool]): Block advertisements
            proxy (Optional[Literal]): Proxy type to use
            extract (Optional[JsonConfig]): Content extraction config
            json_options (Optional[JsonConfig]): JSON extraction config
            actions (Optional[List[Union]]): Actions to perform
            agent (Optional[AgentOptions]): Agent configuration
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlWatcher: An instance to monitor the batch scrape job via WebSocket

        Raises:
            Exception: If batch scrape job fails to start
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "batch_scrape_urls_and_watch")

        scrape_params = {}

        # Add individual parameters
        if formats is not None:
            scrape_params['formats'] = formats
        if headers is not None:
            scrape_params['headers'] = headers
        if include_tags is not None:
            scrape_params['includeTags'] = include_tags
        if exclude_tags is not None:
            scrape_params['excludeTags'] = exclude_tags
        if only_main_content is not None:
            scrape_params['onlyMainContent'] = only_main_content
        if wait_for is not None:
            scrape_params['waitFor'] = wait_for
        if timeout is not None:
            scrape_params['timeout'] = timeout
        if location is not None:
            scrape_params['location'] = location.model_dump(exclude_none=True)
        if mobile is not None:
            scrape_params['mobile'] = mobile
        if skip_tls_verification is not None:
            scrape_params['skipTlsVerification'] = skip_tls_verification
        if remove_base64_images is not None:
            scrape_params['removeBase64Images'] = remove_base64_images
        if block_ads is not None:
            scrape_params['blockAds'] = block_ads
        if proxy is not None:
            scrape_params['proxy'] = proxy
        if extract is not None:
            extract = ensure_schema_dict(extract)
            if isinstance(extract, dict) and "schema" in extract:
                extract["schema"] = ensure_schema_dict(extract["schema"])
            scrape_params['extract'] = extract if isinstance(extract, dict) else extract.model_dump(exclude_none=True)
        if json_options is not None:
            json_options = ensure_schema_dict(json_options)
            if isinstance(json_options, dict) and "schema" in json_options:
                json_options["schema"] = ensure_schema_dict(json_options["schema"])
            
            # Convert to dict if it's a JsonConfig object
            if hasattr(json_options, 'dict'):
                json_options_dict = json_options.model_dump(exclude_none=True)
            else:
                json_options_dict = json_options
            
            # Convert snake_case to camelCase for API
            json_options_api = {}
            if 'prompt' in json_options_dict and json_options_dict['prompt'] is not None:
                json_options_api['prompt'] = json_options_dict['prompt']
            if 'schema' in json_options_dict and json_options_dict['schema'] is not None:
                json_options_api['schema'] = json_options_dict['schema']
            if 'system_prompt' in json_options_dict and json_options_dict['system_prompt'] is not None:
                json_options_api['systemPrompt'] = json_options_dict['system_prompt']
            if 'agent' in json_options_dict and json_options_dict['agent'] is not None:
                json_options_api['agent'] = json_options_dict['agent']
            
            scrape_params['jsonOptions'] = json_options_api
        if actions is not None:
            scrape_params['actions'] = [action.model_dump(exclude_none=True) for action in actions]
        if agent is not None:
            scrape_params['agent'] = agent.model_dump(exclude_none=True)

        # Add any additional kwargs
        scrape_params.update(kwargs)

        # Create final params object
        final_params = ScrapeParams(**scrape_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['urls'] = urls
        params_dict['origin'] = f"python-sdk@{version}"

        if 'extract' in params_dict and params_dict['extract'] and 'schema' in params_dict['extract']:
            params_dict['extract']['schema'] = ensure_schema_dict(params_dict['extract']['schema'])
        if 'jsonOptions' in params_dict and params_dict['jsonOptions'] and 'schema' in params_dict['jsonOptions']:
            params_dict['jsonOptions']['schema'] = ensure_schema_dict(params_dict['jsonOptions']['schema'])

        # Apply format transformation for API
        if 'formats' in params_dict and params_dict['formats']:
            params_dict['formats'] = scrape_formats_transform(params_dict['formats'])

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = self._post_request(f'{self.api_url}/v1/batch/scrape', params_dict, headers)

        if response.status_code == 200:
            try:
                crawl_response = BatchScrapeResponse(**response.json())
                if crawl_response.success and crawl_response.id:
                    return CrawlWatcher(crawl_response.id, self)
                else:
                    raise Exception("Batch scrape job failed to start")
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'start batch scrape job')
    
    def check_batch_scrape_status(self, id: str, poll_interval: int = 2) -> BatchScrapeStatusResponse:
        """
        Check the status of a batch scrape job using the Firecrawl API.

        Args:
            id (str): The ID of the batch scrape job.
            poll_interval (int): The interval in seconds between status checks.
        Returns:
            BatchScrapeStatusResponse: The status of the batch scrape job.

        Raises:
            Exception: If the status check request fails.
        """
        endpoint = f'/v1/batch/scrape/{id}'

        headers = self._prepare_headers()
        response = self._get_request(f'{self.api_url}{endpoint}', headers)
        if response.status_code == 200:
            try:
                status_data = response.json()
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            
            while status_data['status'] != 'completed':
                print(status_data['status'])
                time.sleep(poll_interval)
                response = self._get_request(f'{self.api_url}{endpoint}', headers)
                if response.status_code == 200:
                    status_data = response.json()
                else:
                    self._handle_error(response, 'check batch scrape status')

            if 'data' in status_data:
                data = status_data['data']
                while 'next' in status_data:
                        if len(status_data['data']) == 0:
                            break
                        next_url = status_data.get('next')
                        if not next_url:
                            logger.warning("Expected 'next' URL is missing.")
                            break
                        try:
                            status_response = self._get_request(next_url, headers)
                            if status_response.status_code != 200:
                                logger.error(f"Failed to fetch next page: {status_response.status_code}")
                                break
                            try:
                                next_data = status_response.json()
                            except:
                                raise Exception(f'Failed to parse Firecrawl response as JSON.')
                            data.extend(next_data.get('data', []))
                            status_data = next_data
                        except Exception as e:
                            logger.error(f"Error during pagination request: {e}")
                            break

                # Apply format transformations to each document in the data
                if data:
                    for document in data:
                        scrape_formats_response_transform(document)

            response = {
                'status': status_data.get('status'),
                'total': status_data.get('total'),
                'completed': status_data.get('completed'),
                'credits_used': status_data.get('creditsUsed'),
                'expires_at': status_data.get('expiresAt'),
                'data': data,
                'next': status_data.get('next'),
                'error': status_data.get('error')
            }

            if 'error' in status_data:
                response['error'] = status_data['error']

            if 'next' in status_data:
                response['next'] = status_data['next']

            return BatchScrapeStatusResponse(**response)
        else:
            self._handle_error(response, 'check batch scrape status')

    def check_batch_scrape_errors(self, id: str) -> CrawlErrorsResponse:
        """
        Returns information about batch scrape errors.

        Args:
            id (str): The ID of the crawl job.

        Returns:
            CrawlErrorsResponse containing:
            * errors (List[Dict[str, str]]): List of errors with fields:
              * id (str): Error ID
              * timestamp (str): When the error occurred
              * url (str): URL that caused the error
              * error (str): Error message
            * robotsBlocked (List[str]): List of URLs blocked by robots.txt

        Raises:
            Exception: If the error check request fails
        """
        headers = self._prepare_headers()
        response = self._get_request(f'{self.api_url}/v1/batch/scrape/{id}/errors', headers)
        if response.status_code == 200:
            try:
                return CrawlErrorsResponse(**response.json())
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, "check batch scrape errors")

    def extract(
            self,
            urls: Optional[List[str]] = None,
            *,
            prompt: Optional[str] = None,
            schema: Optional[Any] = None,
            system_prompt: Optional[str] = None,
            allow_external_links: Optional[bool] = False,
            enable_web_search: Optional[bool] = False,
            show_sources: Optional[bool] = False,
            agent: Optional[Dict[str, Any]] = None) -> ExtractResponse[Any]:
        """
        Extract structured information from URLs.

        Args:
            urls (Optional[List[str]]): URLs to extract from
            prompt (Optional[str]): Custom extraction prompt
            schema (Optional[Any]): JSON schema/Pydantic model
            system_prompt (Optional[str]): System context
            allow_external_links (Optional[bool]): Follow external links
            enable_web_search (Optional[bool]): Enable web search
            show_sources (Optional[bool]): Include source URLs
            agent (Optional[Dict[str, Any]]): Agent configuration

        Returns:
            ExtractResponse[Any] with:
            * success (bool): Whether request succeeded
            * data (Optional[Any]): Extracted data matching schema
            * error (Optional[str]): Error message if any

        Raises:
            ValueError: If prompt/schema missing or extraction fails
        """
        headers = self._prepare_headers()

        if not prompt and not schema:
            raise ValueError("Either prompt or schema is required")

        if not urls and not prompt:
            raise ValueError("Either urls or prompt is required")

        if schema:
            schema = ensure_schema_dict(schema)

        request_data = {
            'urls': urls or [],
            'allowExternalLinks': allow_external_links,
            'enableWebSearch': enable_web_search,
            'showSources': show_sources,
            'schema': schema,
            'origin': f'python-sdk@{get_version()}'
        }

        # Only add prompt and systemPrompt if they exist
        if prompt:
            request_data['prompt'] = prompt
        if system_prompt:
            request_data['systemPrompt'] = system_prompt
            
        if agent:
            request_data['agent'] = agent

        try:
            # Send the initial extract request
            response = self._post_request(
                f'{self.api_url}/v1/extract',
                request_data,
                headers
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                except:
                    raise Exception(f'Failed to parse Firecrawl response as JSON.')
                if data['success']:
                    job_id = data.get('id')
                    if not job_id:
                        raise Exception('Job ID not returned from extract request.')

                    # Poll for the extract status
                    while True:
                        status_response = self._get_request(
                            f'{self.api_url}/v1/extract/{job_id}',
                            headers
                        )
                        if status_response.status_code == 200:
                            try:
                                status_data = status_response.json()
                            except:
                                raise Exception(f'Failed to parse Firecrawl response as JSON.')
                            if status_data['status'] == 'completed':
                                return ExtractResponse(**status_data)
                            elif status_data['status'] in ['failed', 'cancelled']:
                                raise Exception(f'Extract job {status_data["status"]}. Error: {status_data["error"]}')
                        else:
                            self._handle_error(status_response, "extract-status")

                        time.sleep(2)  # Polling interval
                else:
                    raise Exception(f'Failed to extract. Error: {data["error"]}')
            else:
                self._handle_error(response, "extract")
        except Exception as e:
            raise ValueError(str(e), 500)

        return ExtractResponse(success=False, error="Internal server error.")
    
    def get_extract_status(self, job_id: str) -> ExtractResponse[Any]:
        """
        Retrieve the status of an extract job.

        Args:
            job_id (str): The ID of the extract job.

        Returns:
            ExtractResponse[Any]: The status of the extract job.

        Raises:
            ValueError: If there is an error retrieving the status.
        """
        headers = self._prepare_headers()
        try:
            response = self._get_request(f'{self.api_url}/v1/extract/{job_id}', headers)
            if response.status_code == 200:
                try:
                    return ExtractResponse(**response.json())
                except:
                    raise Exception(f'Failed to parse Firecrawl response as JSON.')
            else:
                self._handle_error(response, "get extract status")
        except Exception as e:
            raise ValueError(str(e), 500)

    def async_extract(
            self,
            urls: Optional[List[str]] = None,
            *,
            prompt: Optional[str] = None,
            schema: Optional[Any] = None,
            system_prompt: Optional[str] = None,
            allow_external_links: Optional[bool] = False,
            enable_web_search: Optional[bool] = False,
            show_sources: Optional[bool] = False,
            agent: Optional[Dict[str, Any]] = None) -> ExtractResponse[Any]:
        """
        Initiate an asynchronous extract job.

        Args:
            urls (List[str]): URLs to extract information from
            prompt (Optional[str]): Custom extraction prompt
            schema (Optional[Any]): JSON schema/Pydantic model
            system_prompt (Optional[str]): System context
            allow_external_links (Optional[bool]): Follow external links
            enable_web_search (Optional[bool]): Enable web search
            show_sources (Optional[bool]): Include source URLs
            agent (Optional[Dict[str, Any]]): Agent configuration
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests

        Returns:
            ExtractResponse[Any] with:
            * success (bool): Whether request succeeded
            * data (Optional[Any]): Extracted data matching schema
            * error (Optional[str]): Error message if any

        Raises:
            ValueError: If job initiation fails
        """
        headers = self._prepare_headers()
        
        schema = schema
        if schema:
            schema = ensure_schema_dict(schema)

        request_data = {
            'urls': urls,
            'allowExternalLinks': allow_external_links,
            'enableWebSearch': enable_web_search,
            'showSources': show_sources,
            'schema': schema,
            'origin': f'python-sdk@{version}'
        }

        if prompt:
            request_data['prompt'] = prompt
        if system_prompt:
            request_data['systemPrompt'] = system_prompt
        if agent:
            request_data['agent'] = agent

        try:
            response = self._post_request(f'{self.api_url}/v1/extract', request_data, headers)
            if response.status_code == 200:
                try:
                    return ExtractResponse(**response.json())
                except:
                    raise Exception(f'Failed to parse Firecrawl response as JSON.')
            else:
                self._handle_error(response, "async extract")
        except Exception as e:
            raise ValueError(str(e), 500)

    def _prepare_headers(
            self,
            idempotency_key: Optional[str] = None) -> Dict[str, str]:
        """
        Prepare the headers for API requests.

        Args:
            idempotency_key (Optional[str]): A unique key to ensure idempotency of requests.

        Returns:
            Dict[str, str]: The headers including content type, authorization, and optionally idempotency key.
        """
        if idempotency_key:
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'x-idempotency-key': idempotency_key
            }

        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def _post_request(
            self,
            url: str,
            data: Dict[str, Any],
            headers: Dict[str, str],
            retries: int = 3,
            backoff_factor: float = 0.5) -> requests.Response:
        """
        Make a POST request with retries.

        Args:
            url (str): The URL to send the POST request to.
            data (Dict[str, Any]): The JSON data to include in the POST request.
            headers (Dict[str, str]): The headers to include in the POST request.
            retries (int): Number of retries for the request.
            backoff_factor (float): Backoff factor for retries.

        Returns:
            requests.Response: The response from the POST request.

        Raises:
            requests.RequestException: If the request fails after the specified retries.
        """
        for attempt in range(retries):
            response = requests.post(url, headers=headers, json=data, timeout=((data["timeout"] + 5000) if "timeout" in data else None))
            if response.status_code == 502:
                time.sleep(backoff_factor * (2 ** attempt))
            else:
                return response
        return response

    def _get_request(
            self,
            url: str,
            headers: Dict[str, str],
            retries: int = 3,
            backoff_factor: float = 0.5) -> requests.Response:
        """
        Make a GET request with retries.

        Args:
            url (str): The URL to send the GET request to.
            headers (Dict[str, str]): The headers to include in the GET request.
            retries (int): Number of retries for the request.
            backoff_factor (float): Backoff factor for retries.

        Returns:
            requests.Response: The response from the GET request.

        Raises:
            requests.RequestException: If the request fails after the specified retries.
        """
        for attempt in range(retries):
            response = requests.get(url, headers=headers)
            if response.status_code == 502:
                time.sleep(backoff_factor * (2 ** attempt))
            else:
                return response
        return response
    
    def _delete_request(
            self,
            url: str,
            headers: Dict[str, str],
            retries: int = 3,
            backoff_factor: float = 0.5) -> requests.Response:
        """
        Make a DELETE request with retries.

        Args:
            url (str): The URL to send the DELETE request to.
            headers (Dict[str, str]): The headers to include in the DELETE request.
            retries (int): Number of retries for the request.
            backoff_factor (float): Backoff factor for retries.

        Returns:
            requests.Response: The response from the DELETE request.

        Raises:
            requests.RequestException: If the request fails after the specified retries.
        """
        for attempt in range(retries):
            response = requests.delete(url, headers=headers)
            if response.status_code == 502:
                time.sleep(backoff_factor * (2 ** attempt))
            else:
                return response
        return response

    def _monitor_job_status(
            self,
            id: str,
            headers: Dict[str, str],
            poll_interval: int) -> CrawlStatusResponse:
        """
        Monitor the status of a crawl job until completion.

        Args:
            id (str): The ID of the crawl job.
            headers (Dict[str, str]): The headers to include in the status check requests.
            poll_interval (int): Seconds between status checks.

        Returns:
            CrawlStatusResponse: The crawl results if the job is completed successfully.

        Raises:
            Exception: If the job fails or an error occurs during status checks.
        """
        while True:
            api_url = f'{self.api_url}/v1/crawl/{id}'

            status_response = self._get_request(api_url, headers)
            if status_response.status_code == 200:
                try:
                    status_data = status_response.json()
                except:
                    raise Exception(f'Failed to parse Firecrawl response as JSON.')
                if status_data['status'] == 'completed':
                    if 'data' in status_data:
                        data = status_data['data']
                        while 'next' in status_data:
                            if len(status_data['data']) == 0:
                                break
                            status_response = self._get_request(status_data['next'], headers)
                            try:
                                status_data = status_response.json()
                            except:
                                raise Exception(f'Failed to parse Firecrawl response as JSON.')
                            data.extend(status_data.get('data', []))
                        status_data['data'] = data
                        return CrawlStatusResponse(**status_data)
                    else:
                        raise Exception('Crawl job completed but no data was returned')
                elif status_data['status'] in ['active', 'paused', 'pending', 'queued', 'waiting', 'scraping']:
                    poll_interval=max(poll_interval,2)
                    time.sleep(poll_interval)  # Wait for the specified interval before checking again
                else:
                    raise Exception(f'Crawl job failed or was stopped. Status: {status_data["status"]}')
            else:
                self._handle_error(status_response, 'check crawl status')

    def _handle_error(
            self,
            response: requests.Response,
            action: str) -> None:
        """
        Handle errors from API responses.

        Args:
            response (requests.Response): The response object from the API request.
            action (str): Description of the action that was being performed.

        Raises:
            Exception: An exception with a message containing the status code and error details from the response.
        """
        try:
            error_message = response.json().get('error', 'No error message provided.')
            error_details = response.json().get('details', 'No additional error details provided.')
        except:
            raise requests.exceptions.HTTPError(f'Failed to parse Firecrawl error response as JSON. Status code: {response.status_code}', response=response)
        
        message = self._get_error_message(response.status_code, action, error_message, error_details)

        # Raise an HTTPError with the custom message and attach the response
        raise requests.exceptions.HTTPError(message, response=response)

    def _get_error_message(self, status_code: int, action: str, error_message: str, error_details: str) -> str:
        """
        Generate a standardized error message based on HTTP status code.
        
        Args:
            status_code (int): The HTTP status code from the response
            action (str): Description of the action that was being performed
            error_message (str): The error message from the API response
            error_details (str): Additional error details from the API response
            
        Returns:
            str: A formatted error message
        """
        if status_code == 402:
            return f"Payment Required: Failed to {action}. {error_message} - {error_details}"
        elif status_code == 403:
            message = f"Website Not Supported: Failed to {action}. {error_message} - {error_details}"
        elif status_code == 408:
            return f"Request Timeout: Failed to {action} as the request timed out. {error_message} - {error_details}"
        elif status_code == 409:
            return f"Conflict: Failed to {action} due to a conflict. {error_message} - {error_details}"
        elif status_code == 500:
            return f"Internal Server Error: Failed to {action}. {error_message} - {error_details}"
        else:
            return f"Unexpected error during {action}: Status code {status_code}. {error_message} - {error_details}"

    def _validate_kwargs(self, kwargs: Dict[str, Any], method_name: str) -> None:
        """
        Validate additional keyword arguments before they are passed to the API.
        This provides early validation before the Pydantic model validation.

        Args:
            kwargs (Dict[str, Any]): Additional keyword arguments to validate
            method_name (str): Name of the method these kwargs are for

        Raises:
            ValueError: If kwargs contain invalid or unsupported parameters
        """
        if not kwargs:
            return

        # Known parameter mappings for each method
        method_params = {
            "scrape_url": {"formats", "include_tags", "exclude_tags", "only_main_content", "wait_for", 
                          "timeout", "location", "mobile", "skip_tls_verification", "remove_base64_images",
                          "block_ads", "proxy", "extract", "json_options", "actions", "change_tracking_options"},
            "search": {"limit", "tbs", "filter", "lang", "country", "location", "timeout", "scrape_options"},
            "crawl_url": {"include_paths", "exclude_paths", "max_depth", "max_discovery_depth", "limit",
                         "allow_backward_links", "allow_external_links", "ignore_sitemap", "scrape_options",
                         "webhook", "deduplicate_similar_urls", "ignore_query_parameters", "regex_on_full_url"},
            "map_url": {"search", "ignore_sitemap", "include_subdomains", "sitemap_only", "limit", "timeout"},
            "batch_scrape_urls": {"formats", "headers", "include_tags", "exclude_tags", "only_main_content",
                                 "wait_for", "timeout", "location", "mobile", "skip_tls_verification",
                                 "remove_base64_images", "block_ads", "proxy", "extract", "json_options",
                                 "actions", "agent", "webhook"},
            "async_batch_scrape_urls": {"formats", "headers", "include_tags", "exclude_tags", "only_main_content",
                                       "wait_for", "timeout", "location", "mobile", "skip_tls_verification",
                                       "remove_base64_images", "block_ads", "proxy", "extract", "json_options",
                                       "actions", "agent", "webhook"},
            "batch_scrape_urls_and_watch": {"formats", "headers", "include_tags", "exclude_tags", "only_main_content",
                                           "wait_for", "timeout", "location", "mobile", "skip_tls_verification",
                                           "remove_base64_images", "block_ads", "proxy", "extract", "json_options",
                                           "actions", "agent", "webhook"}
        }

        # Get allowed parameters for this method
        allowed_params = method_params.get(method_name, set())
        
        # Check for unknown parameters
        unknown_params = set(kwargs.keys()) - allowed_params
        if unknown_params:
            raise ValueError(f"Unsupported parameter(s) for {method_name}: {', '.join(unknown_params)}. Please refer to the API documentation for the correct parameters.")

        # Additional type validation can be added here if needed
        # For now, we rely on Pydantic models for detailed type validation

class CrawlWatcher:
    """
    A class to watch and handle crawl job events via WebSocket connection.

    Attributes:
        id (str): The ID of the crawl job to watch
        app (FirecrawlApp): The FirecrawlApp instance
        data (List[Dict[str, Any]]): List of crawled documents/data
        status (str): Current status of the crawl job
        ws_url (str): WebSocket URL for the crawl job
        event_handlers (dict): Dictionary of event type to list of handler functions
    """
    def __init__(self, id: str, app: FirecrawlApp):
        self.id = id
        self.app = app
        self.data: List[Dict[str, Any]] = []
        self.status = "scraping"
        self.ws_url = f"{app.api_url.replace('http', 'ws')}/v1/crawl/{id}"
        self.event_handlers = {
            'done': [],
            'error': [],
            'document': []
        }

    async def connect(self) -> None:
        """
        Establishes WebSocket connection and starts listening for messages.
        """
        async with websockets.connect(
            self.ws_url,
            additional_headers=[("Authorization", f"Bearer {self.app.api_key}")]
        ) as websocket:
            await self._listen(websocket)

    async def _listen(self, websocket) -> None:
        """
        Listens for incoming WebSocket messages and handles them.

        Args:
            websocket: The WebSocket connection object
        """
        async for message in websocket:
            msg = json.loads(message)
            await self._handle_message(msg)

    def add_event_listener(self, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Adds an event handler function for a specific event type.

        Args:
            event_type (str): Type of event to listen for ('done', 'error', or 'document')
            handler (Callable): Function to handle the event
        """
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)

    def dispatch_event(self, event_type: str, detail: Dict[str, Any]) -> None:
        """
        Dispatches an event to all registered handlers for that event type.

        Args:
            event_type (str): Type of event to dispatch
            detail (Dict[str, Any]): Event details/data to pass to handlers
        """
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                handler(detail)

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """
        Handles incoming WebSocket messages based on their type.

        Args:
            msg (Dict[str, Any]): The message to handle
        """
        if msg['type'] == 'done':
            self.status = 'completed'
            self.dispatch_event('done', {'status': self.status, 'data': self.data, 'id': self.id})
        elif msg['type'] == 'error':
            self.status = 'failed'
            self.dispatch_event('error', {'status': self.status, 'data': self.data, 'error': msg['error'], 'id': self.id})
        elif msg['type'] == 'catchup':
            self.status = msg['data']['status']
            self.data.extend(msg['data'].get('data', []))
            for doc in self.data:
                self.dispatch_event('document', {'data': doc, 'id': self.id})
        elif msg['type'] == 'document':
            self.data.append(msg['data'])
            self.dispatch_event('document', {'data': msg['data'], 'id': self.id})

class AsyncFirecrawlApp(FirecrawlApp):
    """
    Asynchronous version of FirecrawlApp that implements async methods using aiohttp.
    Provides non-blocking alternatives to all FirecrawlApp operations.
    """

    async def _async_request(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            data: Optional[Dict[str, Any]] = None,
            retries: int = 3,
            backoff_factor: float = 0.5) -> Dict[str, Any]:
        """
        Generic async request method with exponential backoff retry logic.

        Args:
            method (str): The HTTP method to use (e.g., "GET" or "POST").
            url (str): The URL to send the request to.
            headers (Dict[str, str]): Headers to include in the request.
            data (Optional[Dict[str, Any]]): The JSON data to include in the request body (only for POST requests).
            retries (int): Maximum number of retry attempts (default: 3).
            backoff_factor (float): Factor to calculate delay between retries (default: 0.5).
                Delay will be backoff_factor * (2 ** retry_count).

        Returns:
            Dict[str, Any]: The parsed JSON response from the server.

        Raises:
            aiohttp.ClientError: If the request fails after all retries.
            Exception: If max retries are exceeded or other errors occur.
        """
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.request(
                        method=method, url=url, headers=headers, json=data
                    ) as response:
                        if response.status == 502:
                            await asyncio.sleep(backoff_factor * (2 ** attempt))
                            continue
                        if response.status >= 300:
                            await self._handle_error(response, f"make {method} request")
                        return await response.json()
                except aiohttp.ClientError as e:
                    if attempt == retries - 1:
                        raise e
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
            raise Exception("Max retries exceeded")
        
    def _prepare_headers(
            self,
            idempotency_key: Optional[str] = None) -> Dict[str, str]:
        """
        Prepare the headers for API requests.

        Args:
            idempotency_key (Optional[str]): A unique key to ensure idempotency of requests.

        Returns:
            Dict[str, str]: The headers including content type, authorization, and optionally idempotency key.
        """
        if idempotency_key:
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'x-idempotency-key': idempotency_key
            }

        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    async def _async_post_request(
            self, url: str, data: Dict[str, Any], headers: Dict[str, str],
            retries: int = 3, backoff_factor: float = 0.5) -> Dict[str, Any]:
        """
        Make an async POST request with exponential backoff retry logic.

        Args:
            url (str): The URL to send the POST request to.
            data (Dict[str, Any]): The JSON data to include in the request body.
            headers (Dict[str, str]): Headers to include in the request.
            retries (int): Maximum number of retry attempts (default: 3).
            backoff_factor (float): Factor to calculate delay between retries (default: 0.5).
                Delay will be backoff_factor * (2 ** retry_count).

        Returns:
            Dict[str, Any]: The parsed JSON response from the server.

        Raises:
            aiohttp.ClientError: If the request fails after all retries.
            Exception: If max retries are exceeded or other errors occur.
        """
        return await self._async_request("POST", url, headers, data, retries, backoff_factor)

    async def _async_get_request(
            self, url: str, headers: Dict[str, str],
            retries: int = 3, backoff_factor: float = 0.5) -> Dict[str, Any]:
        """
        Make an async GET request with exponential backoff retry logic.

        Args:
            url (str): The URL to send the GET request to.
            headers (Dict[str, str]): Headers to include in the request.
            retries (int): Maximum number of retry attempts (default: 3).
            backoff_factor (float): Factor to calculate delay between retries (default: 0.5).
                Delay will be backoff_factor * (2 ** retry_count).

        Returns:
            Dict[str, Any]: The parsed JSON response from the server.

        Raises:
            aiohttp.ClientError: If the request fails after all retries.
            Exception: If max retries are exceeded or other errors occur.
        """
        return await self._async_request("GET", url, headers, None, retries, backoff_factor)

    async def _handle_error(self, response: aiohttp.ClientResponse, action: str) -> None:
        """
        Handle errors from async API responses with detailed error messages.

        Args:
            response (aiohttp.ClientResponse): The response object from the failed request
            action (str): Description of the action that was being attempted

        Raises:
            aiohttp.ClientError: With a detailed error message based on the response status:
                - 402: Payment Required
                - 408: Request Timeout
                - 409: Conflict
                - 500: Internal Server Error
                - Other: Unexpected error with status code
        """
        try:
            error_data = await response.json()
            error_message = error_data.get('error', 'No error message provided.')
            error_details = error_data.get('details', 'No additional error details provided.')
        except:
            raise aiohttp.ClientError(f'Failed to parse Firecrawl error response as JSON. Status code: {response.status}')

        message = await self._get_async_error_message(response.status, action, error_message, error_details)

        raise aiohttp.ClientError(message)

    async def _get_async_error_message(self, status_code: int, action: str, error_message: str, error_details: str) -> str:
        """
        Generate a standardized error message based on HTTP status code for async operations.
        
        Args:
            status_code (int): The HTTP status code from the response
            action (str): Description of the action that was being performed
            error_message (str): The error message from the API response
            error_details (str): Additional error details from the API response
            
        Returns:
            str: A formatted error message
        """
        return self._get_error_message(status_code, action, error_message, error_details)

    async def crawl_url_and_watch(
            self,
            url: str,
            params: Optional[CrawlParams] = None,
            idempotency_key: Optional[str] = None) -> 'AsyncCrawlWatcher':
        """
        Initiate an async crawl job and return an AsyncCrawlWatcher to monitor progress via WebSocket.

        Args:
          url (str): Target URL to start crawling from
          params (Optional[CrawlParams]): See CrawlParams model for configuration:
            URL Discovery:
            * includePaths - Patterns of URLs to include
            * excludePaths - Patterns of URLs to exclude
            * maxDepth - Maximum crawl depth
            * maxDiscoveryDepth - Maximum depth for finding new URLs
            * limit - Maximum pages to crawl

            Link Following:
            * allowBackwardLinks - Follow parent directory links
            * allowExternalLinks - Follow external domain links  
            * ignoreSitemap - Skip sitemap.xml processing

            Advanced:
            * scrapeOptions - Page scraping configuration
            * webhook - Notification webhook settings
            * deduplicateSimilarURLs - Remove similar URLs
            * ignoreQueryParameters - Ignore URL parameters
            * regexOnFullURL - Apply regex to full URLs
          idempotency_key (Optional[str]): Unique key to prevent duplicate requests

        Returns:
          AsyncCrawlWatcher: An instance to monitor the crawl job via WebSocket

        Raises:
          Exception: If crawl job fails to start
        """
        crawl_response = await self.async_crawl_url(url, params, idempotency_key)
        if crawl_response.get('success') and 'id' in crawl_response:
            return AsyncCrawlWatcher(crawl_response['id'], self)
        else:
            raise Exception("Crawl job failed to start")

    async def batch_scrape_urls_and_watch(
            self,
            urls: List[str],
            params: Optional[ScrapeParams] = None,
            idempotency_key: Optional[str] = None) -> 'AsyncCrawlWatcher':
        """
        Initiate an async batch scrape job and return an AsyncCrawlWatcher to monitor progress.

        Args:
            urls (List[str]): List of URLs to scrape
            params (Optional[ScrapeParams]): See ScrapeParams model for configuration:

              Content Options:
              * formats - Content formats to retrieve
              * includeTags - HTML tags to include
              * excludeTags - HTML tags to exclude
              * onlyMainContent - Extract main content only
              
              Request Options:
              * headers - Custom HTTP headers
              * timeout - Request timeout (ms)
              * mobile - Use mobile user agent
              * proxy - Proxy type
              
              Extraction Options:
              * extract - Content extraction config
              * jsonOptions - JSON extraction config
              * actions - Actions to perform
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests

        Returns:
            AsyncCrawlWatcher: An instance to monitor the batch scrape job via WebSocket

        Raises:
            Exception: If batch scrape job fails to start
        """
        batch_response = await self.async_batch_scrape_urls(urls, params, idempotency_key)
        if batch_response.get('success') and 'id' in batch_response:
            return AsyncCrawlWatcher(batch_response['id'], self)
        else:
            raise Exception("Batch scrape job failed to start")

    async def scrape_url(
            self,
            url: str,
            *,
            formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json", "change_tracking"]]] = None,
            include_tags: Optional[List[str]] = None,
            exclude_tags: Optional[List[str]] = None,
            only_main_content: Optional[bool] = None,
            wait_for: Optional[int] = None,
            timeout: Optional[int] = None,
            location: Optional[LocationConfig] = None,
            mobile: Optional[bool] = None,
            skip_tls_verification: Optional[bool] = None,
            remove_base64_images: Optional[bool] = None,
            block_ads: Optional[bool] = None,
            proxy: Optional[Literal["basic", "stealth"]] = None,
            extract: Optional[JsonConfig] = None,
            json_options: Optional[JsonConfig] = None,
            actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
            change_tracking_options: Optional[ChangeTrackingOptions] = None,
            **kwargs) -> ScrapeResponse[Any]:
        """
        Scrape a single URL asynchronously.

        Args:
          url (str): Target URL to scrape
          formats (Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json", "change_tracking"]]]): Content types to retrieve (markdown/html/etc)
          include_tags (Optional[List[str]]): HTML tags to include
          exclude_tags (Optional[List[str]]): HTML tags to exclude
          only_main_content (Optional[bool]): Extract main content only
          wait_for (Optional[int]): Wait for a specific element to appear
          timeout (Optional[int]): Request timeout (ms)
          location (Optional[LocationConfig]): Location configuration
          mobile (Optional[bool]): Use mobile user agent
          skip_tls_verification (Optional[bool]): Skip TLS verification
          remove_base64_images (Optional[bool]): Remove base64 images
          block_ads (Optional[bool]): Block ads
          proxy (Optional[Literal["basic", "stealth"]]): Proxy type (basic/stealth)
          extract (Optional[JsonConfig]): Content extraction settings
          json_options (Optional[JsonConfig]): JSON extraction settings
          actions (Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]]): Actions to perform
          change_tracking_options (Optional[ChangeTrackingOptions]): Change tracking configuration
          **kwargs: Additional parameters to pass to the API

        Returns:
            ScrapeResponse with:
            * success - Whether scrape was successful
            * markdown - Markdown content if requested
            * html - HTML content if requested
            * raw_html - Raw HTML content if requested
            * links - Extracted links if requested
            * screenshot - Screenshot if requested
            * extract - Extracted data if requested
            * json - JSON data if requested
            * change_tracking - Change tracking data if requested
            * error - Error message if scrape failed

        Raises:
            Exception: If scraping fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "scrape_url")

        headers = self._prepare_headers()

        # Build scrape parameters
        scrape_params = {
            'url': url,
            'origin': f"python-sdk@{version}"
        }

        scrape_params.update(parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            change_tracking_options=change_tracking_options,
            **kwargs
        ))

        # Make async request
        endpoint = f'/v1/scrape'
        response = await self._async_post_request(
            f'{self.api_url}{endpoint}',
            scrape_params,
            headers
        )

        if response.get('success') and 'data' in response:
            data = response['data']
            data = scrape_formats_response_transform(data)
            if 'change_tracking' in data:
                data['change_tracking'] = change_tracking_response_transform(data['change_tracking'])
            return ScrapeResponse(**data)
        elif "error" in response:
            raise Exception(f'Failed to scrape URL. Error: {response["error"]}')
        else:
            # Use the response content directly if possible, otherwise a generic message
            error_content = response.get('error', str(response))
            raise Exception(f'Failed to scrape URL. Error: {error_content}')

    async def batch_scrape_urls(
        self,
        urls: List[str],
        *,
        formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json"]]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        only_main_content: Optional[bool] = None,
        wait_for: Optional[int] = None,
        timeout: Optional[int] = None,
        location: Optional[LocationConfig] = None,
        mobile: Optional[bool] = None,
        skip_tls_verification: Optional[bool] = None,
        remove_base64_images: Optional[bool] = None,
        block_ads: Optional[bool] = None,
        proxy: Optional[Literal["basic", "stealth"]] = None,
        extract: Optional[JsonConfig] = None,
        json_options: Optional[JsonConfig] = None,
        actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
        agent: Optional[AgentOptions] = None,
        poll_interval: Optional[int] = 2,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> BatchScrapeStatusResponse:
        """
        Asynchronously scrape multiple URLs and monitor until completion.

        Args:
            urls (List[str]): URLs to scrape
            formats (Optional[List[Literal]]): Content formats to retrieve
            headers (Optional[Dict[str, str]]): Custom HTTP headers
            include_tags (Optional[List[str]]): HTML tags to include
            exclude_tags (Optional[List[str]]): HTML tags to exclude
            only_main_content (Optional[bool]): Extract main content only
            wait_for (Optional[int]): Wait time in milliseconds
            timeout (Optional[int]): Request timeout in milliseconds
            location (Optional[LocationConfig]): Location configuration
            mobile (Optional[bool]): Use mobile user agent
            skip_tls_verification (Optional[bool]): Skip TLS verification
            remove_base64_images (Optional[bool]): Remove base64 encoded images
            block_ads (Optional[bool]): Block advertisements
            proxy (Optional[Literal]): Proxy type to use
            extract (Optional[JsonConfig]): Content extraction config
            json_options (Optional[JsonConfig]): JSON extraction config
            actions (Optional[List[Union]]): Actions to perform
            agent (Optional[AgentOptions]): Agent configuration
            poll_interval (Optional[int]): Seconds between status checks (default: 2)
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            BatchScrapeStatusResponse with:
            * Scraping status and progress
            * Scraped content for each URL
            * Success/error information

        Raises:
            Exception: If batch scrape fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "batch_scrape_urls")

        scrape_params = parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            agent=agent,
            **kwargs
        )
        
        scrape_params['urls'] = urls
        scrape_params['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = await self._async_post_request(
            f'{self.api_url}/v1/batch/scrape',
            scrape_params,
            headers
        )

        if response.get('success'):
            try:
                id = response.get('id')
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            return await self.check_batch_scrape_status(id, poll_interval)
        else:
            await self._handle_error(response, 'start batch scrape job')


    async def async_batch_scrape_urls(
        self,
        urls: List[str],
        *,
        formats: Optional[List[Literal["markdown", "html", "raw_html", "links", "screenshot", "screenshot@full_page", "extract", "json"]]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        only_main_content: Optional[bool] = None,
        wait_for: Optional[int] = None,
        timeout: Optional[int] = None,
        location: Optional[LocationConfig] = None,
        mobile: Optional[bool] = None,
        skip_tls_verification: Optional[bool] = None,
        remove_base64_images: Optional[bool] = None,
        block_ads: Optional[bool] = None,
        proxy: Optional[Literal["basic", "stealth"]] = None,
        extract: Optional[JsonConfig] = None,
        json_options: Optional[JsonConfig] = None,
        actions: Optional[List[Union[WaitAction, ScreenshotAction, ClickAction, WriteAction, PressAction, ScrollAction, ScrapeAction, ExecuteJavascriptAction]]] = None,
        agent: Optional[AgentOptions] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> BatchScrapeResponse:
        """
        Initiate a batch scrape job asynchronously.

        Args:
            urls (List[str]): URLs to scrape
            formats (Optional[List[Literal]]): Content formats to retrieve
            headers (Optional[Dict[str, str]]): Custom HTTP headers
            include_tags (Optional[List[str]]): HTML tags to include
            exclude_tags (Optional[List[str]]): HTML tags to exclude
            only_main_content (Optional[bool]): Extract main content only
            wait_for (Optional[int]): Wait time in milliseconds
            timeout (Optional[int]): Request timeout in milliseconds
            location (Optional[LocationConfig]): Location configuration
            mobile (Optional[bool]): Use mobile user agent
            skip_tls_verification (Optional[bool]): Skip TLS verification
            remove_base64_images (Optional[bool]): Remove base64 encoded images
            block_ads (Optional[bool]): Block advertisements
            proxy (Optional[Literal]): Proxy type to use
            extract (Optional[JsonConfig]): Content extraction config
            json_options (Optional[JsonConfig]): JSON extraction config
            actions (Optional[List[Union]]): Actions to perform
            agent (Optional[AgentOptions]): Agent configuration
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            BatchScrapeResponse with:
            * success - Whether job started successfully
            * id - Unique identifier for the job
            * url - Status check URL
            * error - Error message if start failed

        Raises:
            Exception: If job initiation fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "async_batch_scrape_urls")

        scrape_params = parse_scrape_options(
            formats=formats,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            location=location,
            mobile=mobile,
            skip_tls_verification=skip_tls_verification,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            proxy=proxy,
            extract=extract,
            json_options=json_options,
            actions=actions,
            agent=agent,
            **kwargs
        )
      
        scrape_params['urls'] = urls
        scrape_params['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = await self._async_post_request(
            f'{self.api_url}/v1/batch/scrape',
            scrape_params,
            headers
        )

        if response.get('success'):
            try:
                return BatchScrapeResponse(**response)
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'start batch scrape job')

    async def crawl_url(
        self,
        url: str,
        *,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_discovery_depth: Optional[int] = None,
        limit: Optional[int] = None,
        allow_backward_links: Optional[bool] = None,
        allow_external_links: Optional[bool] = None,
        ignore_sitemap: Optional[bool] = None,
        scrape_options: Optional[ScrapeOptions] = None,
        webhook: Optional[Union[str, WebhookConfig]] = None,
        deduplicate_similar_urls: Optional[bool] = None,
        ignore_query_parameters: Optional[bool] = None,
        regex_on_full_url: Optional[bool] = None,
        delay: Optional[int] = None,
        poll_interval: Optional[int] = 2,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> CrawlStatusResponse:
        """
        Crawl a website starting from a URL.

        Args:
            url (str): Target URL to start crawling from
            include_paths (Optional[List[str]]): Patterns of URLs to include
            exclude_paths (Optional[List[str]]): Patterns of URLs to exclude
            max_depth (Optional[int]): Maximum crawl depth
            max_discovery_depth (Optional[int]): Maximum depth for finding new URLs
            limit (Optional[int]): Maximum pages to crawl
            allow_backward_links (Optional[bool]): Follow parent directory links
            allow_external_links (Optional[bool]): Follow external domain links
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            scrape_options (Optional[ScrapeOptions]): Page scraping configuration
            webhook (Optional[Union[str, WebhookConfig]]): Notification webhook settings
            deduplicate_similar_urls (Optional[bool]): Remove similar URLs
            ignore_query_parameters (Optional[bool]): Ignore URL parameters
            regex_on_full_url (Optional[bool]): Apply regex to full URLs
            delay (Optional[int]): Delay in seconds between scrapes
            poll_interval (Optional[int]): Seconds between status checks (default: 2)
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlStatusResponse with:
            * Crawling status and progress
            * Crawled page contents
            * Success/error information

        Raises:
            Exception: If crawl fails
        """
        # Validate any additional kwargs
        self._validate_kwargs(kwargs, "crawl_url")

        crawl_params = {}

        # Add individual parameters
        if include_paths is not None:
            crawl_params['includePaths'] = include_paths
        if exclude_paths is not None:
            crawl_params['excludePaths'] = exclude_paths
        if max_depth is not None:
            crawl_params['maxDepth'] = max_depth
        if max_discovery_depth is not None:
            crawl_params['maxDiscoveryDepth'] = max_discovery_depth
        if limit is not None:
            crawl_params['limit'] = limit
        if allow_backward_links is not None:
            crawl_params['allowBackwardLinks'] = allow_backward_links
        if allow_external_links is not None:
            crawl_params['allowExternalLinks'] = allow_external_links
        if ignore_sitemap is not None:
            crawl_params['ignoreSitemap'] = ignore_sitemap
        if scrape_options is not None:
            crawl_params['scrapeOptions'] = scrape_options.model_dump(exclude_none=True)
        if webhook is not None:
            crawl_params['webhook'] = webhook
        if deduplicate_similar_urls is not None:
            crawl_params['deduplicateSimilarURLs'] = deduplicate_similar_urls
        if ignore_query_parameters is not None:
            crawl_params['ignoreQueryParameters'] = ignore_query_parameters
        if regex_on_full_url is not None:
            crawl_params['regexOnFullURL'] = regex_on_full_url
        if delay is not None:
            crawl_params['delay'] = delay

        # Add any additional kwargs
        crawl_params.update(kwargs)

        # Create final params object
        final_params = CrawlParams(**crawl_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"
        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = await self._async_post_request(
          f'{self.api_url}/v1/crawl', params_dict, headers)

        if response.get('success'):
            try:
                id = response.get('id')
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
            return await self._async_monitor_job_status(id, headers, poll_interval)
        else:
            self._handle_error(response, 'start crawl job')


    async def async_crawl_url(
       self,
        url: str,
        *,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_discovery_depth: Optional[int] = None,
        limit: Optional[int] = None,
        allow_backward_links: Optional[bool] = None,
        allow_external_links: Optional[bool] = None,
        ignore_sitemap: Optional[bool] = None,
        scrape_options: Optional[ScrapeOptions] = None,
        webhook: Optional[Union[str, WebhookConfig]] = None,
        deduplicate_similar_urls: Optional[bool] = None,
        ignore_query_parameters: Optional[bool] = None,
        regex_on_full_url: Optional[bool] = None,
        delay: Optional[int] = None,
        poll_interval: Optional[int] = 2,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> CrawlResponse:
        """
        Start an asynchronous crawl job.

        Args:
            url (str): Target URL to start crawling from
            include_paths (Optional[List[str]]): Patterns of URLs to include
            exclude_paths (Optional[List[str]]): Patterns of URLs to exclude
            max_depth (Optional[int]): Maximum crawl depth
            max_discovery_depth (Optional[int]): Maximum depth for finding new URLs
            limit (Optional[int]): Maximum pages to crawl
            allow_backward_links (Optional[bool]): Follow parent directory links
            allow_external_links (Optional[bool]): Follow external domain links
            ignore_sitemap (Optional[bool]): Skip sitemap.xml processing
            scrape_options (Optional[ScrapeOptions]): Page scraping configuration
            webhook (Optional[Union[str, WebhookConfig]]): Notification webhook settings
            deduplicate_similar_urls (Optional[bool]): Remove similar URLs
            ignore_query_parameters (Optional[bool]): Ignore URL parameters
            regex_on_full_url (Optional[bool]): Apply regex to full URLs
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests
            **kwargs: Additional parameters to pass to the API

        Returns:
            CrawlResponse with:
            * success - Whether crawl started successfully
            * id - Unique identifier for the crawl job
            * url - Status check URL for the crawl
            * error - Error message if start failed

        Raises:
            Exception: If crawl initiation fails
        """
        crawl_params = {}

        # Add individual parameters
        if include_paths is not None:
            crawl_params['includePaths'] = include_paths
        if exclude_paths is not None:
            crawl_params['excludePaths'] = exclude_paths
        if max_depth is not None:
            crawl_params['maxDepth'] = max_depth
        if max_discovery_depth is not None:
            crawl_params['maxDiscoveryDepth'] = max_discovery_depth
        if limit is not None:
            crawl_params['limit'] = limit
        if allow_backward_links is not None:
            crawl_params['allowBackwardLinks'] = allow_backward_links
        if allow_external_links is not None:
            crawl_params['allowExternalLinks'] = allow_external_links
        if ignore_sitemap is not None:
            crawl_params['ignoreSitemap'] = ignore_sitemap
        if scrape_options is not None:
            crawl_params['scrapeOptions'] = scrape_options.model_dump(exclude_none=True)
        if webhook is not None:
            crawl_params['webhook'] = webhook
        if deduplicate_similar_urls is not None:
            crawl_params['deduplicateSimilarURLs'] = deduplicate_similar_urls
        if ignore_query_parameters is not None:
            crawl_params['ignoreQueryParameters'] = ignore_query_parameters
        if regex_on_full_url is not None:
            crawl_params['regexOnFullURL'] = regex_on_full_url
        if delay is not None:
            crawl_params['delay'] = delay

        # Add any additional kwargs
        crawl_params.update(kwargs)

        # Create final params object
        final_params = CrawlParams(**crawl_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        headers = self._prepare_headers(idempotency_key)
        response = await self._async_post_request(
          f'{self.api_url}/v1/crawl',
          params_dict,
          headers
        )

        if response.get('success'):
            try:
                return CrawlResponse(**response)
            except:
                raise Exception(f'Failed to parse Firecrawl response as JSON.')
        else:
            self._handle_error(response, 'start crawl job')

    async def check_crawl_status(self, id: str) -> CrawlStatusResponse:
        """
        Check the status and results of an asynchronous crawl job.

        Args:
            id (str): Unique identifier for the crawl job

        Returns:
            CrawlStatusResponse containing:
            Status Information:
            * status - Current state (scraping/completed/failed/cancelled)
            * completed - Number of pages crawled
            * total - Total pages to crawl
            * creditsUsed - API credits consumed
            * expiresAt - Data expiration timestamp
            
            Results:
            * data - List of crawled documents
            * next - URL for next page of results (if paginated)
            * success - Whether status check succeeded
            * error - Error message if failed

        Raises:
            Exception: If status check fails
        """
        headers = self._prepare_headers()
        endpoint = f'/v1/crawl/{id}'
        
        status_data = await self._async_get_request(
            f'{self.api_url}{endpoint}',
            headers
        )

        if status_data.get('status') == 'completed':
            if 'data' in status_data:
                data = status_data['data']
                while 'next' in status_data:
                    if len(status_data['data']) == 0:
                        break
                    next_url = status_data.get('next')
                    if not next_url:
                        logger.warning("Expected 'next' URL is missing.")
                        break
                    next_data = await self._async_get_request(next_url, headers)
                    data.extend(next_data.get('data', []))
                    status_data = next_data
                status_data['data'] = data
        # Create CrawlStatusResponse object from status data
        response = CrawlStatusResponse(
            status=status_data.get('status'),
            total=status_data.get('total'),
            completed=status_data.get('completed'),
            creditsUsed=status_data.get('creditsUsed'),
            expiresAt=status_data.get('expiresAt'),
            data=data,
            success=False if 'error' in status_data else True
        )

        if 'error' in status_data:
            response.error = status_data.get('error')

        if 'next' in status_data:
            response.next = status_data.get('next')

        return response

    async def _async_monitor_job_status(self, id: str, headers: Dict[str, str], poll_interval: int = 2) -> CrawlStatusResponse:
        """
        Monitor the status of an asynchronous job until completion.

        Args:
            id (str): The ID of the job to monitor
            headers (Dict[str, str]): Headers to include in status check requests
            poll_interval (int): Seconds between status checks (default: 2)

        Returns:
            CrawlStatusResponse: The job results if completed successfully

        Raises:
            Exception: If the job fails or an error occurs during status checks
        """
        while True:
            status_data = await self._async_get_request(
                f'{self.api_url}/v1/crawl/{id}',
                headers
            )

            if status_data.get('status') == 'completed':
                if 'data' in status_data:
                    data = status_data['data']
                    while 'next' in status_data:
                        if len(status_data['data']) == 0:
                            break
                        next_url = status_data.get('next')
                        if not next_url:
                            logger.warning("Expected 'next' URL is missing.")
                            break
                        next_data = await self._async_get_request(next_url, headers)
                        data.extend(next_data.get('data', []))
                        status_data = next_data
                    status_data['data'] = data
                    return CrawlStatusResponse(**status_data)
                else:
                    raise Exception('Job completed but no data was returned')
            elif status_data.get('status') in ['active', 'paused', 'pending', 'queued', 'waiting', 'scraping']:
                await asyncio.sleep(max(poll_interval, 2))
            else:
                raise Exception(f'Job failed or was stopped. Status: {status_data["status"]}')

    async def map_url(
        self,
        url: str,
        *,
        search: Optional[str] = None,
        ignore_sitemap: Optional[bool] = None,
        include_subdomains: Optional[bool] = None,
        sitemap_only: Optional[bool] = None,
        limit: Optional[int] = None,
        timeout: Optional[int] = None,
        params: Optional[MapParams] = None) -> MapResponse:
        """
        Asynchronously map and discover links from a URL.

        Args:
          url (str): Target URL to map
          params (Optional[MapParams]): See MapParams model:
            Discovery Options:
            * search - Filter pattern for URLs
            * ignoreSitemap - Skip sitemap.xml
            * includeSubdomains - Include subdomain links
            * sitemapOnly - Only use sitemap.xml
            
            Limits:
            * limit - Max URLs to return
            * timeout - Request timeout (ms)

        Returns:
          MapResponse with:
          * Discovered URLs
          * Success/error status

        Raises:
          Exception: If mapping fails
        """
        map_params = {}
        if params:
            map_params.update(params.model_dump(exclude_none=True))

        # Add individual parameters
        if search is not None:
            map_params['search'] = search
        if ignore_sitemap is not None:
            map_params['ignoreSitemap'] = ignore_sitemap
        if include_subdomains is not None:
            map_params['includeSubdomains'] = include_subdomains
        if sitemap_only is not None:
            map_params['sitemapOnly'] = sitemap_only
        if limit is not None:
            map_params['limit'] = limit
        if timeout is not None:
            map_params['timeout'] = timeout

        # Create final params object
        final_params = MapParams(**map_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['url'] = url
        params_dict['origin'] = f"python-sdk@{version}"

        # Make request
        endpoint = f'/v1/map'
        response = await self._async_post_request(
            f'{self.api_url}{endpoint}',
            params_dict,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )

        if response.get('success') and 'links' in response:
            return MapResponse(**response)
        elif 'error' in response:
            raise Exception(f'Failed to map URL. Error: {response["error"]}')
        else:
            raise Exception(f'Failed to map URL. Error: {response}')

    async def extract(
            self,
            urls: Optional[List[str]] = None,
            *,
            prompt: Optional[str] = None,
            schema: Optional[Any] = None,
            system_prompt: Optional[str] = None,
            allow_external_links: Optional[bool] = False,
            enable_web_search: Optional[bool] = False,
            show_sources: Optional[bool] = False,
            agent: Optional[Dict[str, Any]] = None) -> ExtractResponse[Any]:
            
        """
        Asynchronously extract structured information from URLs.

        Args:
            urls (Optional[List[str]]): URLs to extract from
            prompt (Optional[str]): Custom extraction prompt
            schema (Optional[Any]): JSON schema/Pydantic model
            system_prompt (Optional[str]): System context
            allow_external_links (Optional[bool]): Follow external links
            enable_web_search (Optional[bool]): Enable web search
            show_sources (Optional[bool]): Include source URLs
            agent (Optional[Dict[str, Any]]): Agent configuration

        Returns:
          ExtractResponse with:
          * Structured data matching schema
          * Source information if requested
          * Success/error status

        Raises:
          ValueError: If prompt/schema missing or extraction fails
        """
        headers = self._prepare_headers()

        if not prompt and not schema:
            raise ValueError("Either prompt or schema is required")

        if not urls and not prompt:
            raise ValueError("Either urls or prompt is required")

        if schema:
            schema = ensure_schema_dict(schema)

        request_data = {
            'urls': urls or [],
            'allowExternalLinks': allow_external_links,
            'enableWebSearch': enable_web_search,
            'showSources': show_sources,
            'schema': schema,
            'origin': f'python-sdk@{get_version()}'
        }

        # Only add prompt and systemPrompt if they exist
        if prompt:
            request_data['prompt'] = prompt
        if system_prompt:
            request_data['systemPrompt'] = system_prompt
            
        if agent:
            request_data['agent'] = agent

        response = await self._async_post_request(
            f'{self.api_url}/v1/extract',
            request_data,
            headers
        )

        if response.get('success'):
            job_id = response.get('id')
            if not job_id:
                raise Exception('Job ID not returned from extract request.')

            while True:
                status_data = await self._async_get_request(
                    f'{self.api_url}/v1/extract/{job_id}',
                    headers
                )

                if status_data['status'] == 'completed':
                    return ExtractResponse(**status_data)
                elif status_data['status'] in ['failed', 'cancelled']:
                    raise Exception(f'Extract job {status_data["status"]}. Error: {status_data["error"]}')

                await asyncio.sleep(2)
        else:
            raise Exception(f'Failed to extract. Error: {response.get("error")}')

    async def check_batch_scrape_status(self, id: str, poll_interval: int = 2) -> BatchScrapeStatusResponse:
        """
        Check the status of a batch scrape job using the Firecrawl API.

        Args:
            id (str): The ID of the batch scrape job.
            poll_interval (int): The interval in seconds between status checks.
        Returns:
            BatchScrapeStatusResponse: The status of the batch scrape job.

        Raises:
            Exception: If the status check request fails.
        """
        endpoint = f'/v1/batch/scrape/{id}'

        headers = self._prepare_headers()
        response = await self._async_get_request(f'{self.api_url}{endpoint}', headers)

        try:
            while response.get('status') != 'completed':
                await asyncio.sleep(poll_interval)
                response = await self._async_get_request(f'{self.api_url}{endpoint}', headers)

                if 'data' in response:
                    data = response.get('data')
                    while 'next' in response:
                        if len(response.get('data')) == 0:
                            break
                        next_url = response.get('next')
                        if not next_url:
                            logger.warning("Expected 'next' URL is missing.")
                            break
                        try:
                            response = await self._async_get_request(next_url, headers)
                            next_data = response.get('data')
                            if next_data:
                                data.extend(next_data.get('data', []))
                        except Exception as e:
                            logger.error(f"Error during pagination request: {e}")
                            break

                    # Apply format transformations to each document in the data
                    if data:
                        for document in data:
                            scrape_formats_response_transform(document)

            response = {
                'status': response.get('status'),
                'total': response.get('total'),
                'completed': response.get('completed'),
                'credits_used': response.get('creditsUsed'),
                'expires_at': response.get('expiresAt'),
                'data': data,
                'next': response.get('next'),
                'error': response.get('error')
            }

            return BatchScrapeStatusResponse(**response)
        
        except Exception as e:
            await self._handle_error(response, 'check batch scrape status')

    async def check_batch_scrape_errors(self, id: str) -> CrawlErrorsResponse:
        """
        Get information about errors from an asynchronous batch scrape job.

        Args:
          id (str): The ID of the batch scrape job

        Returns:
          CrawlErrorsResponse containing:
            errors (List[Dict[str, str]]): List of errors with fields:
              * id (str): Error ID
              * timestamp (str): When the error occurred
              * url (str): URL that caused the error
              * error (str): Error message
          * robotsBlocked (List[str]): List of URLs blocked by robots.txt

        Raises:
          Exception: If error check fails
        """
        headers = self._prepare_headers()
        return await self._async_get_request(
            f'{self.api_url}/v1/batch/scrape/{id}/errors',
            headers
        )

    async def check_crawl_errors(self, id: str) -> CrawlErrorsResponse:
        """
        Get information about errors from an asynchronous crawl job.

        Args:
            id (str): The ID of the crawl job

        Returns:
            CrawlErrorsResponse containing:
            * errors (List[Dict[str, str]]): List of errors with fields:
                - id (str): Error ID
                - timestamp (str): When the error occurred
                - url (str): URL that caused the error
                - error (str): Error message
            * robotsBlocked (List[str]): List of URLs blocked by robots.txt

        Raises:
            Exception: If error check fails
        """
        headers = self._prepare_headers()
        return await self._async_get_request(
            f'{self.api_url}/v1/crawl/{id}/errors',
            headers
        )

    async def cancel_crawl(self, id: str) -> Dict[str, Any]:
        """
        Cancel an asynchronous crawl job.

        Args:
            id (str): The ID of the crawl job to cancel

        Returns:
            Dict[str, Any] containing:
            * success (bool): Whether cancellation was successful
            * error (str, optional): Error message if cancellation failed

        Raises:
            Exception: If cancellation fails
        """
        headers = self._prepare_headers()
        async with aiohttp.ClientSession() as session:
            async with session.delete(f'{self.api_url}/v1/crawl/{id}', headers=headers) as response:
                return await response.json()

    async def get_extract_status(self, job_id: str) -> ExtractResponse[Any]:
        """
        Check the status of an asynchronous extraction job.

        Args:
            job_id (str): The ID of the extraction job

        Returns:
            ExtractResponse[Any] with:
            * success (bool): Whether request succeeded
            * data (Optional[Any]): Extracted data matching schema
            * error (Optional[str]): Error message if any
            * warning (Optional[str]): Warning message if any
            * sources (Optional[List[str]]): Source URLs if requested

        Raises:
            ValueError: If status check fails
        """
        headers = self._prepare_headers()
        try:
            return await self._async_get_request(
                f'{self.api_url}/v1/extract/{job_id}',
                headers
            )
        except Exception as e:
            raise ValueError(str(e))

    async def async_extract(
            self,
            urls: Optional[List[str]] = None,
            *,
            prompt: Optional[str] = None,
            schema: Optional[Any] = None,
            system_prompt: Optional[str] = None,
            allow_external_links: Optional[bool] = False,
            enable_web_search: Optional[bool] = False,
            show_sources: Optional[bool] = False,
            agent: Optional[Dict[str, Any]] = None) -> ExtractResponse[Any]:
        """
        Initiate an asynchronous extraction job without waiting for completion.

        Args:
            urls (Optional[List[str]]): URLs to extract from
            prompt (Optional[str]): Custom extraction prompt
            schema (Optional[Any]): JSON schema/Pydantic model
            system_prompt (Optional[str]): System context
            allow_external_links (Optional[bool]): Follow external links
            enable_web_search (Optional[bool]): Enable web search
            show_sources (Optional[bool]): Include source URLs
            agent (Optional[Dict[str, Any]]): Agent configuration
            idempotency_key (Optional[str]): Unique key to prevent duplicate requests

        Returns:
            ExtractResponse[Any] with:
            * success (bool): Whether request succeeded
            * data (Optional[Any]): Extracted data matching schema
            * error (Optional[str]): Error message if any

        Raises:
            ValueError: If job initiation fails
        """
        headers = self._prepare_headers()

        if not prompt and not schema:
            raise ValueError("Either prompt or schema is required")

        if not urls and not prompt:
            raise ValueError("Either urls or prompt is required")

        if schema:
            schema = ensure_schema_dict(schema)

        request_data = ExtractResponse(
            urls=urls or [],
            allowExternalLinks=allow_external_links,
            enableWebSearch=enable_web_search,
            showSources=show_sources,
            schema=schema,
            origin=f'python-sdk@{version}'
        )

        if prompt:
            request_data['prompt'] = prompt
        if system_prompt:
            request_data['systemPrompt'] = system_prompt
        if agent:
            request_data['agent'] = agent

        try:
            return await self._async_post_request(
                f'{self.api_url}/v1/extract',
                request_data,
                headers
            )
        except Exception as e:
            raise ValueError(str(e))

    async def search(
            self,
            query: str,
            *,
            limit: Optional[int] = None,
            tbs: Optional[str] = None,
            filter: Optional[str] = None,
            lang: Optional[str] = None,
            country: Optional[str] = None,
            location: Optional[str] = None,
            timeout: Optional[int] = None,
            scrape_options: Optional[ScrapeOptions] = None,
            params: Optional[Union[Dict[str, Any], SearchParams]] = None,
            **kwargs) -> SearchResponse:
        """
        Asynchronously search for content using Firecrawl.

        Args:
            query (str): Search query string
            limit (Optional[int]): Max results (default: 5)
            tbs (Optional[str]): Time filter (e.g. "qdr:d")
            filter (Optional[str]): Custom result filter
            lang (Optional[str]): Language code (default: "en")
            country (Optional[str]): Country code (default: "us") 
            location (Optional[str]): Geo-targeting
            timeout (Optional[int]): Request timeout in milliseconds
            scrape_options (Optional[ScrapeOptions]): Result scraping configuration
            params (Optional[Union[Dict[str, Any], SearchParams]]): Additional search parameters
            **kwargs: Additional keyword arguments for future compatibility

        Returns:
            SearchResponse: Response containing:
                * success (bool): Whether request succeeded
                * data (List[FirecrawlDocument]): Search results
                * warning (Optional[str]): Warning message if any
                * error (Optional[str]): Error message if any

        Raises:
            Exception: If search fails or response cannot be parsed
        """
        # Build search parameters
        search_params = {}
        if params:
            if isinstance(params, dict):
                search_params.update(params)
            else:
                search_params.update(params.model_dump(exclude_none=True))

        # Add individual parameters
        if limit is not None:
            search_params['limit'] = limit
        if tbs is not None:
            search_params['tbs'] = tbs
        if filter is not None:
            search_params['filter'] = filter
        if lang is not None:
            search_params['lang'] = lang
        if country is not None:
            search_params['country'] = country
        if location is not None:
            search_params['location'] = location
        if timeout is not None:
            search_params['timeout'] = timeout
        if scrape_options is not None:
            search_params['scrapeOptions'] = scrape_options.model_dump(exclude_none=True)
        
        # Add any additional kwargs
        search_params.update(kwargs)

        # Create final params object
        final_params = SearchParams(query=query, **search_params)
        params_dict = final_params.model_dump(exclude_none=True)
        params_dict['origin'] = f"python-sdk@{version}"

        return await self._async_post_request(
            f"{self.api_url}/v1/search",
            params_dict,
            {"Authorization": f"Bearer {self.api_key}"}
        )

class AsyncCrawlWatcher(CrawlWatcher):
    """
    Async version of CrawlWatcher that properly handles async operations.
    """
    def __init__(self, id: str, app: AsyncFirecrawlApp):
        super().__init__(id, app)

    async def connect(self) -> None:
        """
        Establishes async WebSocket connection and starts listening for messages.
        """
        async with websockets.connect(
            self.ws_url,
            additional_headers=[("Authorization", f"Bearer {self.app.api_key}")]
        ) as websocket:
            await self._listen(websocket)

    async def _listen(self, websocket) -> None:
        """
        Listens for incoming WebSocket messages and handles them asynchronously.

        Args:
            websocket: The WebSocket connection object
        """
        async for message in websocket:
            msg = json.loads(message)
            await self._handle_message(msg)

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """
        Handles incoming WebSocket messages based on their type asynchronously.

        Args:
            msg (Dict[str, Any]): The message to handle
        """
        if msg['type'] == 'done':
            self.status = 'completed'
            self.dispatch_event('done', {'status': self.status, 'data': self.data, 'id': self.id})
        elif msg['type'] == 'error':
            self.status = 'failed'
            self.dispatch_event('error', {'status': self.status, 'data': self.data, 'error': msg['error'], 'id': self.id})
        elif msg['type'] == 'catchup':
            self.status = msg['data']['status']
            self.data.extend(msg['data'].get('data', []))
            for doc in self.data:
                self.dispatch_event('document', {'data': doc, 'id': self.id})
        elif msg['type'] == 'document':
            self.data.append(msg['data'])
            self.dispatch_event('document', {'data': msg['data'], 'id': self.id})

    async def _handle_error(self, response: aiohttp.ClientResponse, action: str) -> None:
        """
        Handle errors from async API responses.
        """
        try:
            error_data = await response.json()
            error_message = error_data.get('error', 'No error message provided.')
            error_details = error_data.get('details', 'No additional error details provided.')
        except:
            raise aiohttp.ClientError(f'Failed to parse Firecrawl error response as JSON. Status code: {response.status}')

        # Use the app's method to get the error message
        message = await self.app._get_async_error_message(response.status, action, error_message, error_details)

        raise aiohttp.ClientError(message)

    async def _get_async_error_message(self, status_code: int, action: str, error_message: str, error_details: str) -> str:
        """
        Generate a standardized error message based on HTTP status code for async operations.
        
        Args:
            status_code (int): The HTTP status code from the response
            action (str): Description of the action that was being performed
            error_message (str): The error message from the API response
            error_details (str): Additional error details from the API response
            
        Returns:
            str: A formatted error message
        """
        return self._get_error_message(status_code, action, error_message, error_details)
