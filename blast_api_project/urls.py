"""blast_api_project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views

from rest_framework.documentation import include_docs_urls

urlpatterns = [
    path('api/v1/call-control/', include('callcontrol.urls')),
    path('api/v1/', include('blast_api.urls')),
    path('accounts/login/', auth_views.LoginView.as_view()),
    path('admin/', admin.site.urls),
    path('docs/', include_docs_urls(title='CarrierX SimpleBlast API'))
]
