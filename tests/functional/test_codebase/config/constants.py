# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Application constants."""

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Cache
CACHE_TTL = 3600  # seconds
CACHE_MAX_ENTRIES = 1000

# API
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# Validation
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 20
MIN_PASSWORD_LENGTH = 8

# Order
MAX_ORDER_ITEMS = 50
ORDER_EXPIRY_HOURS = 24

# Product
MAX_PRODUCT_NAME_LENGTH = 200
MAX_PRODUCT_DESCRIPTION_LENGTH = 5000

# Rate Limiting
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds

# File sizes
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

# Date formats
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
