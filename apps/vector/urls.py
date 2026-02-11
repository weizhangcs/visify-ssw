from django.urls import path

from . import views

app_name = "vector"

urlpatterns = [
    path("search/", views.vector_search_view, name="vector_search"),
    path("api/search/", views.vector_search_api, name="vector_search_api"),
]
