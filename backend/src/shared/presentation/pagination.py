"""Paginación estándar de la API."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LargePagination(PageNumberPagination):
    """Para listados densos y de solo lectura (transcripciones, chunks)."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500
